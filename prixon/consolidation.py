from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from prixon.registry import ActionRegistry
from prixon.store import AgentStore


class MacroPromoter:
    """Proposes parameterized macros from repeated successful plan shapes."""

    PARAMETER_KEYS = {"application", "file", "level", "setting"}

    def __init__(self, store: AgentStore, registry: ActionRegistry, minimum_successes: int = 3) -> None:
        self.store = store
        self.registry = registry
        self.minimum_successes = minimum_successes

    def _template(self, plan: dict[str, Any]) -> dict[str, Any]:
        steps = []
        for index, step in enumerate(plan.get("steps", [])):
            action = self.registry.get(step.get("tool", ""))
            args = dict(step.get("args") or {})
            safe_args = {
                key: f"$input.{key}" for key in args if key in self.PARAMETER_KEYS
            }
            dependencies = step.get("depends_on", [])
            if action and action.target_type == "window" and index > 0:
                safe_args = {"window": "$previous.window", "hwnd": "$previous.hwnd"}
                dependencies = sorted(set(dependencies + [index - 1]))
            steps.append({
                "tool": step["tool"],
                "args": safe_args,
                "depends_on": dependencies,
                "expected_outcome": step.get("expected_outcome", "verified"),
            })
        return {"goal": plan.get("goal", "Approved personal routine"), "steps": steps}

    def _shape(self, plan: dict[str, Any]) -> dict[str, Any]:
        shape_steps = []
        for step in plan.get("steps", []):
            action = self.registry.get(step.get("tool", ""))
            shape_steps.append({
                "tool": step.get("tool"),
                "target_type": action.target_type if action else "unknown",
                "argument_types": sorted((step.get("args") or {}).keys()),
                "dependency_count": len(step.get("depends_on", [])),
            })
        return {"steps": shape_steps}

    def consolidate(self) -> dict[str, Any]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        shapes: dict[str, dict[str, Any]] = {}
        for episode in self.store.successful_episodes():
            shape = self._shape(episode["plan"])
            encoded = json.dumps(shape, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]
            groups[digest].append(episode)
            shapes[digest] = shape
        proposed = []
        for digest, episodes in groups.items():
            if len(episodes) < self.minimum_successes:
                continue
            latest = episodes[0]
            first_tool = latest["plan"].get("steps", [{}])[0].get("tool", "routine")
            name = f"Routine {first_tool.replace('.', ' ').title()}"
            template = self._template(latest["plan"])
            # Store the occurrence count once per consolidation run; repeated runs do not inflate trust.
            triggers = sorted({item["utterance"] for item in episodes})
            for trigger in triggers[:12]:
                self.store.record_macro(
                    digest, name, template, trigger, approved=False,
                    evidence_count=len(episodes) if trigger == triggers[0] else 0,
                )
            proposed.append({
                "shape_hash": digest, "name": name, "successes": len(episodes),
                "trigger_phrases": sorted({item["utterance"] for item in episodes})[:12],
                "plan_template": template, "approved": False,
            })
        self.store.audit("macro_consolidation", {"proposals": len(proposed)})
        return {"proposals": proposed, "count": len(proposed)}

    def approve(self, macro_id: int, approved: bool = True) -> bool:
        changed = self.store.approve_macro(macro_id, approved)
        if changed:
            self.store.audit("macro_approval_changed", {"macro_id": macro_id, "approved": approved})
        return changed
