from __future__ import annotations

import re

from prixon.registry import ActionRegistry
from prixon.schemas import Candidate, IntentClass, RouteResult, RiskTier


def normalize(text: str) -> str:
    value = text.casefold().strip()
    value = re.sub(r"[^\\w\\s%.-]", " ", value)
    value = re.sub(r"\\s+", " ", value)
    return value


def classify(text: str) -> IntentClass:
    value = normalize(text)
    if any(word in value for word in ("delete", "move", "rename", "quarantine", "copy")):
        return IntentClass.FILE_OPERATION
    if any(word in value for word in ("volume", "brightness", "wifi", "bluetooth", "setting")):
        return IntentClass.SYSTEM_SETTING
    if any(word in value for word in ("open ", "launch ", "start ", "fire up ")):
        return IntentClass.LAUNCH
    if any(word in value for word in ("minimize", "maximize", "close window", "restore window")):
        return IntentClass.CONTROL
    if any(word in value for word in ("list ", "show ", "what ", "how ", "is ", "check ")):
        return IntentClass.QUERY
    return IntentClass.CHAT


class IntentRouter:
    """Rules-first retrieval. Embedding/LLM arbitration is intentionally a later layer."""

    def __init__(self, registry: ActionRegistry | None = None) -> None:
        self.registry = registry or ActionRegistry()

    def route(self, utterance: str) -> RouteResult:
        normalized = normalize(utterance)
        intent_class = classify(normalized)
        if not normalized:
            return RouteResult(
                status="clarify", normalized_text="", reason="empty_utterance",
                clarification="What would you like Prixon to do?",
            )

        candidates: list[Candidate] = []
        for action in self.registry.by_class(intent_class):
            phrases = (action.name.replace(".", " "), *action.examples)
            best = max((self._phrase_score(normalized, phrase) for phrase in phrases), default=0)
            if best > 0:
                candidates.append(Candidate(action=action, score=best, matched_by="lexical"))

        candidates.sort(key=lambda item: item.score, reverse=True)
        if not candidates:
            return RouteResult(
                status="unresolved", normalized_text=normalized, intent_class=intent_class,
                reason="no_grounded_registry_match",
            )

        best = candidates[0]
        margin = best.score - (candidates[1].score if len(candidates) > 1 else 0)
        required_slots_present = self._has_required_slots(normalized, best.action.required_slots)
        if best.score < 0.42 or (len(candidates) > 1 and margin < 0.08):
            return RouteResult(
                status="clarify", normalized_text=normalized, intent_class=intent_class,
                candidates=candidates[:5], confidence=best.score,
                reason="low_match_or_ambiguous",
                clarification="Did you mean " + " or ".join(
                    c.action.description.lower() for c in candidates[:2]
                ) + "?",
            )
        if not required_slots_present:
            return RouteResult(
                status="clarify", normalized_text=normalized, intent_class=intent_class,
                candidates=candidates[:5], confidence=best.score,
                reason="required_slot_missing",
                clarification=f"What {', '.join(best.action.required_slots)} should I use?",
            )
        return RouteResult(
            status="selected", normalized_text=normalized, intent_class=intent_class,
            candidates=candidates[:5], selected_action=best.action.name,
            confidence=best.score, reason="rules_first_registry_match",
            requires_confirmation=best.action.risk == RiskTier.ALWAYS_CONFIRM,
        )

    @staticmethod
    def _phrase_score(text: str, phrase: str) -> float:
        target = normalize(phrase)
        if not target:
            return 0
        if text == target:
            return 1.0
        if target in text:
            return 0.92
        tokens = set(target.split())
        words = set(text.split())
        if not tokens:
            return 0
        overlap = len(tokens & words) / len(tokens)
        return round(overlap * 0.78, 4)

    @staticmethod
    def _has_required_slots(text: str, slots: tuple[str, ...]) -> bool:
        if not slots:
            return True
        if "application" in slots:
            return bool(re.search(r"\\b(open|launch|start|fire up)\\s+\\w+", text))
        if "level" in slots:
            return bool(re.search(r"\\b\\d{1,3}\\s*%?\\b", text))
        if "window" in slots:
            return any(word in text for word in ("this window", "foreground", "notepad", "chrome"))
        if "file" in slots:
            return any(token in text for token in ("file", "document", "this one", "selected"))
        return False
