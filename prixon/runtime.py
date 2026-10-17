from __future__ import annotations

import logging
import re
import time
from typing import Any

from prixon.confidence import DecisionSignals, fuse_confidence, meets_risk_threshold
from prixon.config import PrixonSettings
from prixon.embeddings import FastEmbedAdapter, SemanticRetriever
from prixon.entities import EntityIndex, ReferenceResolver
from prixon.executor import ActionExecutor, ExecutionBudget
from prixon.kill_switch import KillSwitch
from prixon.learning import OwnerLexicon
from prixon.ollama import OllamaClient
from prixon.perception import WindowsPerception
from prixon.planner import validate_plan
from prixon.proactive import ProactiveEngine
from prixon.registry import ActionRegistry
from prixon.router import IntentRouter
from prixon.schemas import (
    ActionSpec,
    AgentPlan,
    IntentClass,
    PlanStep,
    RiskTier,
    ThoughtRecord,
)
from prixon.store import AgentStore

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Coordinates deterministic reflex routing and bounded deliberate planning."""

    QUERY_RESPONSES = {
        "system.status": "System status is available.",
        "system.battery": "Battery status is available.",
        "system.memory": "Memory usage is available.",
        "system.cpu": "Processor usage is available.",
        "system.wifi": "Wi-Fi adapter status is available.",
        "system.network": "Network adapter status is available.",
        "system.audio": "Master audio level is available.",
        "process.list": "Running processes are listed.",
        "app.is_running": "Application running state is available.",
    }

    SETTING_TERMS = {
        "display": ("display", "screen"),
        "sound": ("sound", "audio"),
        "wifi": ("wifi", "wireless"),
        "bluetooth": ("bluetooth",),
        "battery": ("battery", "battery saver"),
        "night light": ("night light",),
        "focus": ("focus assist", "do not disturb", "quiet hours"),
        "network": ("network", "internet"),
        "windows update": ("windows update", "updates"),
    }

    def __init__(
        self, *, store: AgentStore | None = None, registry: ActionRegistry | None = None,
        perception: WindowsPerception | None = None, ollama: OllamaClient | None = None,
    ) -> None:
        self.settings = PrixonSettings()
        self.store = store or AgentStore()
        self.registry = registry or ActionRegistry()
        self.perception = perception or WindowsPerception()
        self.references = ReferenceResolver()
        self.lexicon = OwnerLexicon(self.store)
        self.ollama = ollama or OllamaClient(
            self.settings.ollama_base_url, self.settings.ollama_model,
            self.settings.ollama_timeout_seconds, self.settings.ollama_keep_alive,
        )
        self.kill_switch = KillSwitch()
        self.executor = ActionExecutor(
            self.registry, self.store, self.perception, self.kill_switch,
            budget=ExecutionBudget(
                max_steps=self.settings.agent_max_plan_steps,
                wall_clock_seconds=self.settings.agent_wall_clock_seconds,
                step_timeout_seconds=self.settings.agent_step_timeout_seconds,
            ),
        )
        self.proactive = ProactiveEngine(self.store)
        self.semantic: SemanticRetriever | None = None
        if self.settings.semantic_enabled:
            try:
                self.semantic = SemanticRetriever(self.registry, FastEmbedAdapter(), self.store)
            except (RuntimeError, OSError, ValueError):
                logger.exception("Semantic retrieval unavailable; deterministic path remains active")
        self.index = EntityIndex(
            self.store, self.semantic.embedder if self.semantic is not None else None,
        )
        self._suggestions: list[dict[str, Any]] = []
        self._loop = None
        self._entity_refresh_at = 0.0
        self._entity_refresh_result = {"applications": 0, "processes": 0, "windows": 0}
        self._register_approved_macros()

    def _register_approved_macros(self) -> None:
        from prixon.router import classify
        approved_macros = self.store.macros(approved=True)
        approved_ids = {str(item["id"]) for item in approved_macros}
        for action in self.registry.all():
            if action.name.startswith("macro."):
                macro_id = action.name.split(".", 2)[1]
                if macro_id not in approved_ids:
                    self.registry.unregister(action.name)
        for macro in approved_macros:
            risk_values = [self.registry.get(step["tool"]).risk for step in macro["plan"].get("steps", [])
                           if self.registry.get(step["tool"])]
            risk_order = {
                RiskTier.READ_ONLY: 0, RiskTier.REVERSIBLE: 1,
                RiskTier.ROUTINE: 2, RiskTier.ALWAYS_CONFIRM: 3,
            }
            inherited_risk = max(risk_values, key=lambda value: risk_order[value]) if risk_values else RiskTier.ALWAYS_CONFIRM
            # Owner approval permits L3 only when no constituent action is L4.
            risk = RiskTier.ALWAYS_CONFIRM if inherited_risk == RiskTier.ALWAYS_CONFIRM else RiskTier.ROUTINE
            groups: dict[IntentClass, list[str]] = {}
            for phrase in macro["trigger_phrases"]:
                intent = classify(phrase)
                groups.setdefault(intent, []).append(phrase)
            for intent, phrases in groups.items():
                action_name = f"macro.{macro['id']}.{intent.value}"
                if self.registry.get(action_name):
                    continue
                self.registry.register(ActionSpec(
                    name=action_name,
                    description=f"Run approved personal routine: {macro['name']}",
                    examples=tuple(phrases) + (macro["name"].casefold(),),
                    intent_class=intent,
                    verb_type="run_macro",
                    target_type="macro",
                    risk=risk,
                    undo_supported=all(
                        self.registry.get(step["tool"]).undo_supported
                        for step in macro["plan"].get("steps", [])
                        if self.registry.get(step["tool"])
                    ),
                ))

    def _macro_id_for_action(self, action_name: str) -> int | None:
        if not action_name.startswith("macro."):
            return None
        try:
            return int(action_name.split(".", 2)[1])
        except (IndexError, ValueError):
            return None

    def list_macros(self, approved: bool | None = None) -> list[dict[str, Any]]:
        return self.store.macros(approved)

    async def run_macro(
        self, macro_id: int, supplied_args: dict[str, Any] | None = None, *,
        execute: bool = False, confirmed: bool = False, session_id: str = "local-session",
    ) -> dict[str, Any]:
        macro = next((item for item in self.store.macros(approved=True) if item["id"] == macro_id), None)
        if not macro:
            return {"status": "not_found_or_not_approved"}
        raw_plan = macro["plan"]
        steps = []
        for raw_step in raw_plan.get("steps", []):
            step_args = dict(raw_step.get("args") or {})
            for key, value in list(step_args.items()):
                if isinstance(value, str) and value.startswith("$input."):
                    input_name = value.removeprefix("$input.")
                    if input_name not in (supplied_args or {}):
                        return {"status": "clarify", "clarification": f"Provide {input_name} for this routine."}
                    step_args[key] = supplied_args[input_name]
            if supplied_args:
                for key in ("application", "file", "level", "setting"):
                    if key in supplied_args and key in self.registry.get(raw_step["tool"]).required_slots:
                        step_args[key] = supplied_args[key]
            if not (step_args.get("hwnd") == "$previous.hwnd"):
                step_args, clarification = self._fill_args(
                    raw_step["tool"], macro["name"], step_args,
                )
                if clarification:
                    return {"status": "clarify", "clarification": clarification}
            steps.append(PlanStep(
                tool=raw_step["tool"], args=step_args,
                depends_on=raw_step.get("depends_on", []),
                expected_outcome=raw_step.get("expected_outcome", "verified"),
                confidence=float(raw_step.get("confidence", 0.85)),
            ))
        plan = AgentPlan(goal=macro["name"], steps=steps)
        validation = validate_plan(plan, self.registry, self.settings.agent_max_plan_steps)
        if not validation.valid:
            return {"status": "rejected", "reason": "macro_plan_invalid", "errors": validation.errors}
        if not execute:
            return {"status": "planned", "macro": macro["name"],
                    "plan": plan.model_dump(mode="json")}
        if any(self.registry.get(step.tool).risk == RiskTier.ALWAYS_CONFIRM for step in plan.steps) and not confirmed:
            return {"status": "confirmation_required", "macro": macro["name"]}
        result = self.executor.execute_plan(plan, confirmed=confirmed, session_id=session_id)
        self.store.episode(
            macro["name"], ["macro", "executor", "verifier"],
            plan.model_dump(mode="json"),
            "success" if result["status"] == "completed" else "failure",
            result.get("reason"),
        )
        return {"status": result["status"], "macro": macro["name"], "execution": result}

    def refresh_entities(self, force: bool = True) -> dict[str, int]:
        if not force and time.monotonic() - self._entity_refresh_at < 15:
            return dict(self._entity_refresh_result)
        apps = self.perception.installed_apps()
        app_count = self.index.refresh("application", apps)
        processes = self.perception.processes(limit=1000)
        process_count = self.index.refresh(
            "process",
            [{"name": item["name"], "target": str(item["pid"]), **item}
             for item in processes if item.get("name")],
        )
        foreground = self.perception.snapshot().get("foreground_window")
        window_count = 0
        if foreground and foreground.get("sensitive"):
            self.references.clear()
        if foreground and foreground.get("title") and not foreground.get("sensitive"):
            window_count = self.index.refresh("window", [{
                "name": foreground["title"], "target": str(foreground["handle"]),
                **foreground,
            }])
            self.references.remember({
                "kind": "window", "name": foreground["title"],
                "target": str(foreground["handle"]), "hwnd": foreground["handle"],
            })
        self._entity_refresh_at = time.monotonic()
        self._entity_refresh_result = {
            "applications": app_count, "processes": process_count, "windows": window_count,
        }
        return dict(self._entity_refresh_result)

    def situation(self) -> dict[str, Any]:
        snapshot = self.perception.snapshot()
        foreground = snapshot.get("foreground_window")
        if foreground and foreground.get("sensitive"):
            foreground = None
        return {
            "foreground_app": foreground,
            "open_windows": [foreground] if foreground else [],
            "system": {
                "cpu_percent": snapshot["cpu_percent"],
                "memory_percent": snapshot["memory"]["percent"],
                "battery": snapshot["battery"],
            },
            "active_goals": self.store.goals(),
        }

    @staticmethod
    def split_compound(text: str) -> list[str]:
        parts = re.split(
            r"\s+(?:and then|then|after that)\s+|\s+and\s+(?=(?:open|launch|start|"
            r"minimize|restore|set|check|show|list|quarantine)\b)",
            text, flags=re.IGNORECASE,
        )
        return [part.strip(" ,.") for part in parts if part.strip(" ,.")]

    def _fill_args(
        self, action_name: str, text: str, supplied: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str | None]:
        args = dict(supplied or {})
        snapshot = self.perception.snapshot()
        foreground = snapshot.get("foreground_window")
        if action_name in {"app.launch", "app.is_running"}:
            if action_name == "app.launch":
                match = re.search(
                    r"\b(?:open|launch|start|fire up)\s+(.+?)(?:\s+please)?$", text, re.I,
                )
            else:
                match = re.search(
                    r"\b(?:is|check if|whether)\s+(.+?)\s+(?:is\s+)?(?:running|open|active)\b",
                    text, re.I,
                )
            # Prefer the entity named in the owner's utterance over any model-proposed slot.
            mention = match.group(1).strip(" .") if match else str(args.get("application") or "").strip()
            if not mention:
                prompt = "Which application should I check?" if action_name == "app.is_running" else "Which installed application should I open?"
                return args, prompt
            args["application"] = mention
            if action_name == "app.launch":
                entity = self.index.resolve(
                    mention, "application",
                    context={"foreground_app": (foreground or {}).get("title")},
                )
                if not entity:
                    self.refresh_entities()
                    entity = self.index.resolve(mention, "application")
                if not entity:
                    return args, f"I couldn't ground '{mention}' to an installed Start Menu application."
                args["application_target"] = entity["target"]
        elif action_name in {"window.minimize", "window.maximize", "window.restore", "window.close"}:
            if args.get("hwnd") == "$previous.hwnd":
                args["window"] = args.get("window", "$previous.window")
                return args, None
            if foreground and foreground.get("sensitive"):
                return args, "This window is classified as a sensitive credential or authentication dialog and is off-limits."
            recent = self.references.resolve("it") if re.search(r"\b(it|that|this|that one)\b", text, re.I) else None
            if recent and recent.get("hwnd"):
                args["window"] = str(recent.get("name") or "recent window")
                args["hwnd"] = int(recent["hwnd"])
            elif foreground and foreground.get("handle") and not foreground.get("sensitive"):
                args["window"] = str(foreground.get("title") or foreground["handle"])
                args["hwnd"] = int(foreground["handle"])
            else:
                return args, "There is no grounded foreground window to control."
        elif action_name == "volume.set":
            match = re.search(r"\b(\d{1,3})\s*%?", text)
            if match:
                args["level"] = float(match.group(1))
            elif "level" not in args:
                return args, "What volume level should I set, from 0 to 100?"
        elif action_name == "settings.open":
            setting = str(args.get("setting") or "").casefold()
            if not setting:
                for candidate, terms in self.SETTING_TERMS.items():
                    if any(term in text.casefold() for term in terms):
                        setting = candidate
                        break
            if not setting:
                return args, "Which Settings page should I open?"
            args["setting"] = setting
        elif action_name == "file.quarantine":
            if "file" not in args:
                return args, "Specify the exact file path to quarantine."
        return args, None

    def _shortlist(self, route) -> list[dict[str, Any]]:
        # Arbitration is only permitted when deterministic retrieval has grounded candidates.
        actions = [candidate.action for candidate in route.candidates[:5]]
        return [
            {"name": action.name, "description": action.description,
             "examples": list(action.examples[:3]),
             "required_slots": list(action.required_slots),
             "risk": action.risk.value,
             "hard_negatives": list(action.hard_negatives[:3])}
            for action in actions
        ]

    async def preview(
        self, text: str, *, trusted_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._register_approved_macros()
        self.refresh_entities(force=False)
        normalized = " ".join(text.casefold().split())
        alias_used = False
        route = IntentRouter(self.registry, self.store).route(normalized)
        arbitration: dict[str, Any] | None = None
        if route.status != "selected" and self.semantic is not None:
            try:
                retrieved = await __import__("asyncio").to_thread(self.semantic.retrieve, normalized, 8)
                best_by_action: dict[str, float] = {}
                for item in retrieved:
                    best_by_action[item.action_name] = max(
                        best_by_action.get(item.action_name, 0.0), item.score,
                    )
                compatible = [
                    (self.registry.get(name), score)
                    for name, score in best_by_action.items()
                    if self.registry.get(name) is not None
                    and self.registry.get(name).intent_class == route.intent_class
                ]
                compatible.sort(key=lambda item: item[1], reverse=True)
                if compatible and compatible[0][1] >= 0.55:
                    from prixon.schemas import Candidate
                    action, score = compatible[0]
                    margin = score - (compatible[1][1] if len(compatible) > 1 else 0.0)
                    if margin >= 0.06:
                        route.status = "selected"
                        route.selected_action = action.name
                        route.confidence = score
                        route.reason = "bge_semantic_retrieval"
                        route.candidates = [Candidate(action=action, score=score, matched_by="fastembed")]
            except Exception as exc:
                logger.info("Semantic retrieval unavailable for this request: %s", exc)
        if route.status != "selected":
            tools = self._shortlist(route)
            if tools:
                try:
                    arbitration = await self.ollama.arbitrate(
                        text, tools, self.situation(), self.store.recent_episodes(3),
                    )
                    action = self.registry.get(str(arbitration.get("action")))
                    if action:
                        confidence_hint = float(arbitration.get("confidence", 0))
                        if arbitration.get("clarification"):
                            return {
                                "status": "clarify",
                                "reason": "model_requested_clarification",
                                "clarification": str(arbitration["clarification"]),
                                "candidates": [candidate.model_dump(mode="json") for candidate in route.candidates],
                            }
                        if confidence_hint < 0.65:
                            second = await self.ollama.arbitrate(
                                text, tools, self.situation(), self.store.recent_episodes(3),
                                temperature=0.1,
                            )
                            if second.get("clarification") or second.get("action") != arbitration.get("action"):
                                return {
                                    "status": "clarify",
                                    "reason": "low_confidence_self_consistency_disagreement",
                                    "candidates": [candidate.model_dump(mode="json") for candidate in route.candidates],
                                    "clarification": "Two local interpretations disagreed. Please clarify which action you intended.",
                                }
                            confidence_hint = min(confidence_hint, float(second.get("confidence", 0)))
                            arbitration["confidence"] = confidence_hint
                        route.status = "selected"
                        route.selected_action = action.name
                        route.confidence = confidence_hint
                        route.reason = "local_ollama_shortlist_arbitration"
                        # Do not promote model-proposed argument values to grounded slots.
                        route.slots = {}
                except Exception as exc:
                    logger.info("Local arbitration unavailable: %s", exc)

        action = self.registry.get(route.selected_action) if route.selected_action else None
        if not action:
            return {
                "status": route.status, "intent_class": route.intent_class.value if route.intent_class else None,
                "action": None, "args": {}, "confidence": route.confidence,
                "reason": route.reason, "clarification": route.clarification,
                "candidates": [candidate.model_dump(mode="json") for candidate in route.candidates],
            }

        alias_used = any(
            alias["target_type"] == "action"
            and alias["target"] == action.name
            and alias["phrase"] in normalized
            for alias in self.store.aliases()
        ) or action.name.startswith("macro.")
        args, clarification = self._fill_args(
            text=text, action_name=action.name, supplied=trusted_args,
        )
        if clarification:
            route.status = "clarify"
        grounded = sum(1 for slot in action.required_slots if args.get(slot) not in (None, ""))
        slot_score = grounded / len(action.required_slots) if action.required_slots else 1.0
        candidate_scores = [candidate.score for candidate in route.candidates]
        margin = (
            max(0.0, candidate_scores[0] - candidate_scores[1])
            if len(candidate_scores) > 1 else candidate_scores[0] if candidate_scores else 0.0
        )
        llm_score = float(arbitration.get("confidence", 0)) if arbitration else 0.0
        foreground = self.situation().get("foreground_app")
        confidence = fuse_confidence(DecisionSignals(
            retrieval_margin=margin,
            slot_grounding=slot_score,
            llm_confidence=llm_score,
            context_prior=1.0 if foreground else 0.5,
            user_lexicon_hit=1.0 if alias_used else 0.0,
        ))
        return {
            "status": route.status, "intent_class": route.intent_class.value if route.intent_class else None,
            "action": action.name, "args": args, "confidence": confidence,
            "risk": action.risk.value,
            "requires_confirmation": action.risk == RiskTier.ALWAYS_CONFIRM,
            "execution_allowed_by_threshold": meets_risk_threshold(confidence, action.risk.value),
            "reason": route.reason, "clarification": clarification or route.clarification,
            "candidates": [candidate.model_dump(mode="json") for candidate in route.candidates],
            "thought": arbitration.get("thought") if arbitration else None,
            "model_metrics": self.ollama.last_metrics,
        }

    def matching_approved_macro(self, text: str) -> int | None:
        normalized = " ".join(text.casefold().split())
        matches: list[tuple[int, int]] = []
        for macro in self.store.macros(approved=True):
            for phrase in macro["trigger_phrases"]:
                candidate = " ".join(str(phrase).casefold().split())
                if candidate and (candidate == normalized or candidate in normalized):
                    matches.append((len(candidate), int(macro["id"])))
        return max(matches)[1] if matches else None

    async def run_request(
        self, text: str, args: dict[str, Any] | None = None, *,
        execute: bool = False, confirmed: bool = False, session_id: str = "local-session",
    ) -> dict[str, Any]:
        self._discard_rephrased_pending_learning(text, session_id)
        matching_macro = self.matching_approved_macro(text)
        if matching_macro is not None:
            macro_preview = await self.preview(text)
            macro_action = self.registry.get(str(macro_preview.get("action") or ""))
            if (
                macro_preview.get("status") != "selected"
                or self._macro_id_for_action(str(macro_preview.get("action") or "")) != matching_macro
                or macro_action is None
                or (execute and not meets_risk_threshold(
                    float(macro_preview.get("confidence", 0.0)), RiskTier.ROUTINE.value,
                ))
            ):
                return {
                    "status": "clarify",
                    "reason": "approved_macro_trigger_below_confidence_gate",
                    "confidence": macro_preview.get("confidence", 0.0),
                }
            return await self.run_macro(
                matching_macro, args or {}, execute=execute,
                confirmed=confirmed, session_id=session_id,
            )
        clauses = self.split_compound(text)
        if len(clauses) > 1:
            return await self._run_compound(
                text, clauses, args or {}, execute=execute,
                confirmed=confirmed, session_id=session_id,
            )
        preview = await self.preview(text, trusted_args=args or {})
        if preview.get("status") != "selected":
            return preview
        macro_id = self._macro_id_for_action(str(preview.get("action") or ""))
        if macro_id is not None:
            return await self.run_macro(
                macro_id, args or {}, execute=execute, confirmed=confirmed, session_id=session_id,
            )
        merged_args = dict(preview.get("args") or {})
        action_name = preview["action"]
        merged_args, grounding_error = self._fill_args(action_name, text, merged_args)
        if grounding_error:
            return {"status": "clarify", "clarification": grounding_error}
        action = self.registry.get(action_name)
        if action is None:
            return {"status": "rejected", "reason": "unknown_action"}
        for slot in action.required_slots:
            if merged_args.get(slot) in (None, ""):
                return {"status": "clarify", "clarification": f"What {slot} should I use?"}
        plan = AgentPlan(
            goal=text,
            steps=[PlanStep(
                tool=action_name, args=merged_args,
                expected_outcome=", ".join(action.postconditions),
                confidence=float(preview.get("confidence", 0.0)),
            )],
            thought=ThoughtRecord(
                observation="Fresh local machine snapshot and grounded action candidate.",
                hypothesis=f"Owner request maps to {action_name}.",
                next_action=action_name,
                expected_outcome=", ".join(action.postconditions),
            ),
        )
        validation = validate_plan(plan, self.registry, self.settings.agent_max_plan_steps)
        self.store.audit("plan_validated", {
            "goal": text, "valid": validation.valid, "errors": validation.errors,
        })
        if not validation.valid:
            return {"status": "rejected", "reason": "plan_validation_failed", "errors": validation.errors}
        if not execute and action.risk != RiskTier.READ_ONLY:
            return {**preview, "plan": plan.model_dump(mode="json"), "plan_validation": validation.model_dump()}
        confidence = float(preview.get("confidence", 0))
        if action.risk == RiskTier.ALWAYS_CONFIRM and not confirmed:
            return {"status": "confirmation_required", "action": action_name, "args": merged_args}
        if action.risk != RiskTier.ALWAYS_CONFIRM and not meets_risk_threshold(confidence, action.risk.value):
            return {
                "status": "clarify", "reason": "confidence_below_risk_threshold",
                "confidence": confidence, "risk": action.risk.value,
            }
        result = self.executor.execute_action(
            action_name, merged_args, confirmed=confirmed, confidence=confidence,
            utterance=text, session_id=session_id,
        )
        outcome = "success" if result.success else "failure"
        self.store.episode(text, ["L0", "L1", "L2"], plan.model_dump(mode="json"), outcome, result.error)
        self.store.audit("request_finished", {
            "utterance": text, "action": action_name, "success": result.success,
            "verified": result.verified, "confidence": confidence,
        })
        if result.success:
            self.store.queue_learning_signal(
                text, action_name, session_id, action.risk.value, result.undo_id,
            )
        else:
            self.lexicon.observe(
                text, action_name, success=False, session_id=session_id,
                risk=action.risk, explicit=False,
            )
        response_text = self.format_observation(action_name, result.output) if result.success else None
        return {
            "status": "completed" if result.success else "failed",
            "action": action_name, "answer": response_text,
            "output": result.output, "error": result.error,
            "verified": result.verified, "undo_id": result.undo_id,
            "confidence": confidence, "plan": plan.model_dump(mode="json"),
        }

    async def _run_compound(
        self, original: str, clauses: list[str], args: dict[str, Any], *,
        execute: bool, confirmed: bool, session_id: str,
    ) -> dict[str, Any]:
        situation = self.situation()
        clause_routes = [IntentRouter(self.registry, self.store).route(clause) for clause in clauses]
        if any(not route.candidates for route in clause_routes):
            return {
                "status": "clarify", "reason": "compound_clause_not_grounded",
                "clarification": "I could not retrieve a registered action for every part of that request.",
                "clauses": [
                    {"text": clause, "status": route.status, "reason": route.reason}
                    for clause, route in zip(clauses, clause_routes, strict=True)
                ],
            }
        shortlist_by_name: dict[str, Any] = {}
        for route in clause_routes:
            candidates = route.candidates[:2] if route.status == "clarify" else route.candidates[:1]
            for candidate in candidates:
                shortlist_by_name.setdefault(candidate.action.name, candidate.action)
        actions = list(shortlist_by_name.values())[:5]
        tools = [
            {"name": item.name, "description": item.description,
             "required_slots": list(item.required_slots), "risk": item.risk.value,
             "examples": list(item.examples[:3]),
             "hard_negatives": list(item.hard_negatives[:3])}
            for item in actions
        ]
        try:
            model_plan = await self.ollama.create_plan(
                original, tools, situation, self.settings.agent_max_plan_steps,
            )
            plan = AgentPlan.model_validate(model_plan)
        except Exception as exc:
            return {
                "status": "clarify", "reason": "compound_planning_unavailable",
                "detail": type(exc).__name__,
                "clarification": "Local planning is unavailable. Split this request into smaller steps.",
            }
        if len(plan.steps) != len(clauses):
            return {"status": "clarify", "reason": "plan_clause_count_mismatch",
                    "clarification": "Please separate the requested steps more clearly."}
        for index, step in enumerate(plan.steps):
            action = self.registry.get(step.tool)
            if action is None:
                return {"status": "rejected", "reason": "unknown_tool", "tool": step.tool}
            # Keep only explicit owner slots and validated step-to-step references.
            owner_args = {
                key: args[key] for key in action.required_slots if key in args
            }
            reference_args = {
                key: value for key, value in step.args.items()
                if isinstance(value, str) and value.startswith("$previous.")
            }
            trusted_step_args = {**owner_args, **reference_args}
            enriched, clarification = self._fill_args(
                step.tool, clauses[index], trusted_step_args,
            )
            if clarification:
                return {"status": "clarify", "clarification": clarification,
                        "plan": plan.model_dump(mode="json")}
            step.args = enriched
            route = IntentRouter(self.registry, self.store).route(clauses[index])
            retrieved_names = {candidate.action.name for candidate in route.candidates[:5]}
            if (
                (route.status == "selected" and route.selected_action != step.tool)
                or (route.status == "clarify" and step.tool not in retrieved_names)
            ):
                return {
                    "status": "clarify", "reason": "planner_and_reflex_disagree",
                    "clause": clauses[index], "planned_action": step.tool,
                    "reflex_action": route.selected_action,
                    "clarification": "The plan selected an action outside the grounded candidate set.",
                }
            grounded = sum(1 for slot in action.required_slots if step.args.get(slot) not in (None, ""))
            slot_score = grounded / len(action.required_slots) if action.required_slots else 1.0
            chosen_score = next(
                (candidate.score for candidate in route.candidates if candidate.action.name == step.tool),
                0.0,
            )
            remaining = sorted(
                (candidate.score for candidate in route.candidates if candidate.action.name != step.tool),
                reverse=True,
            )
            margin = max(0.0, chosen_score - (remaining[0] if remaining else 0.0))
            step.confidence = fuse_confidence(DecisionSignals(
                retrieval_margin=margin,
                slot_grounding=slot_score,
                llm_confidence=float(step.confidence),
                context_prior=1.0 if situation.get("foreground_app") else 0.5,
                user_lexicon_hit=0.0,
            ))
            if action.risk != RiskTier.ALWAYS_CONFIRM and not meets_risk_threshold(
                step.confidence, action.risk.value,
            ):
                return {
                    "status": "clarify", "reason": "compound_step_below_risk_threshold",
                    "step": index, "confidence": step.confidence, "risk": action.risk.value,
                }
        validation = validate_plan(plan, self.registry, self.settings.agent_max_plan_steps)
        if not validation.valid:
            return {"status": "rejected", "reason": "plan_validation_failed", "errors": validation.errors}
        if not execute and any(
            self.registry.get(step.tool).risk != RiskTier.READ_ONLY for step in plan.steps
        ):
            return {"status": "planned", "plan": plan.model_dump(mode="json"),
                    "validation": validation.model_dump()}
        if any(self.registry.get(step.tool).risk == RiskTier.ALWAYS_CONFIRM for step in plan.steps) and not confirmed:
            return {"status": "confirmation_required", "plan": plan.model_dump(mode="json")}
        result = self.executor.execute_plan(plan, confirmed=confirmed)
        outcome = "success" if result["status"] == "completed" else "failure"
        self.store.episode(original, ["L3", "L4", "L5"], plan.model_dump(mode="json"), outcome, result.get("reason"))
        return {"status": result["status"], "execution": result, "plan": plan.model_dump(mode="json")}

    def _discard_rephrased_pending_learning(self, text: str, session_id: str) -> int:
        normalized = " ".join(text.casefold().split())
        discarded = 0
        for pending in self.store.pending_learning_signals(older_than=time.time()):
            if pending["session_id"] != session_id:
                continue
            is_correction = normalized.startswith((
                "no ", "not ", "stop ", "undo ", "actually ", "i meant ",
                "i said ", "wrong ", "not that ", "that's not ",
            )) or " i meant " in normalized
            if is_correction:
                discarded += self.store.discard_pending_learning(signal_id=pending["id"])
                self.store.add_negative_example(pending["phrase"], pending["action_name"])
        return discarded

    def process_pending_learning(self, delay_seconds: int = 30) -> dict[str, int]:
        cutoff = time.time() - max(1, delay_seconds)
        promoted = 0
        discarded = 0
        for pending in self.store.pending_learning_signals(older_than=cutoff):
            if pending["undo_id"]:
                undo = self.store.undo_record(pending["undo_id"])
                if not undo or undo["status"] in {"undone", "failed"}:
                    discarded += self.store.discard_pending_learning(signal_id=pending["id"])
                    continue
            action = self.registry.get(pending["action_name"])
            if action is None:
                discarded += self.store.discard_pending_learning(signal_id=pending["id"])
                continue
            result = self.lexicon.observe(
                pending["phrase"], pending["action_name"], success=True,
                session_id=pending["session_id"], risk=action.risk, explicit=False,
            )
            if self.semantic is not None:
                self.semantic.add_example(pending["action_name"], pending["phrase"])
            promoted += int(result.status == "promoted")
            self.store.discard_pending_learning(signal_id=pending["id"])
        return {"processed": promoted + discarded, "promoted": promoted, "discarded": discarded}

    @staticmethod
    def format_observation(action_name: str, output: dict[str, Any]) -> str:
        if action_name == "system.status":
            memory = output.get("memory", {})
            battery = output.get("battery")
            battery_text = (
                f" Battery is {battery.get('percent')}%."
                if isinstance(battery, dict) else ""
            )
            return (
                f"CPU is at {output.get('cpu_percent', 'unknown')}%; "
                f"memory is at {memory.get('percent', 'unknown')}%.{battery_text}"
            )
        if action_name == "system.memory":
            return (
                f"RAM usage is {output.get('percent', 'unknown')}%. "
                f"{int(output.get('available_bytes', 0)) // (1024**3)} GB is available."
            )
        if action_name == "system.cpu":
            return (
                f"CPU usage is {output.get('cpu_percent', 'unknown')}% across "
                f"{output.get('logical_cores', 'unknown')} logical cores."
            )
        if action_name == "system.wifi":
            state = "connected" if output.get("connected") else "not connected"
            return f"Wi-Fi is {state}. Adapters: {len(output.get('adapters', []))}."
        if action_name == "system.audio":
            return f"Master volume is {output.get('volume', 'unknown')}%."
        if action_name == "system.battery":
            battery = output.get("battery")
            if not battery:
                return "No battery telemetry is available on this device."
            power = "plugged in" if battery.get("plugged_in") else "on battery"
            return f"Battery is at {battery.get('percent')}% ({power})."
        if action_name == "app.is_running":
            return (
                f"{output.get('application')} is "
                f"{'running' if output.get('running') else 'not running'}."
            )
        if action_name == "process.list":
            count = len(output.get("processes", []))
            return f"I found {count} running processes."
        if action_name == "system.network":
            return (
                f"Network traffic counters: {output.get('bytes_received', 0)} bytes received, "
                f"{output.get('bytes_sent', 0)} bytes sent."
            )
        return "The requested observation completed."

    def create_goal(
        self, description: str, priority: int, plan: AgentPlan | None,
        confirmed: bool = False,
    ) -> str:
        payload = {"plan": plan.model_dump(mode="json"), "confirmed": confirmed} if plan else {}
        goal_id = self.store.add_goal(description, priority, "user", payload)
        self.store.audit("goal_created", {"goal_id": goal_id, "description": description, "priority": priority})
        return goal_id

    def undo(self, undo_id: str) -> dict[str, Any]:
        record = self.store.undo_record(undo_id)
        if not record:
            return {"status": "not_found"}
        if record["status"] != "pending":
            return {"status": "already_processed", "current_status": record["status"]}
        try:
            success = self.executor.adapters.undo(
                record["action_name"], record["args"], record["before_state"],
                record.get("output", {}),
            )
            error = None
        except Exception as exc:
            success, error = False, f"{type(exc).__name__}:{exc}"
        self.store.finish_undo(undo_id, "undone" if success else "failed")
        # Requesting an undo is negative owner feedback even if the OS rejected rollback.
        self.store.discard_pending_learning(undo_id=undo_id)
        action = self.registry.get(record["action_name"])
        if action and record.get("utterance"):
            self.lexicon.observe(
                record["utterance"], record["action_name"], success=False,
                session_id=record.get("session_id", "local-session"),
                risk=action.risk, explicit=False,
            )
        self.store.audit("undo_attempted", {"undo_id": undo_id, "success": success, "error": error})
        return {"status": "undone" if success else "failed", "error": error}
