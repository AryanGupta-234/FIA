from __future__ import annotations

import re

from prixon.registry import ActionRegistry
from prixon.schemas import Candidate, IntentClass, RiskTier, RouteResult


def normalize(text: str) -> str:
    value = text.casefold().strip()
    value = re.sub(r"[^\w\s%.-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def classify(text: str) -> IntentClass:
    value = normalize(text)
    if any(term in value for term in (
        "quarantine", "delete file", "move file", "rename file", "copy file",
        "isolate this file", "isolate file",
    )):
        return IntentClass.FILE_OPERATION
    if any(term in value for term in (
        "open wifi settings", "open wi-fi settings", "open battery settings",
        "open bluetooth settings", "open sound settings", "open display settings",
        "open night light settings", "open focus assist settings",
    )) or re.search(r"\b(?:set|change|adjust)\s+(?:the\s+)?(?:volume|brightness|wifi|wi-fi)\b", value) or re.search(
        r"\b(?:turn|lower|raise|increase|decrease|mute|unmute)\b.*\bvolume\b|\bvolume\s+at\s+\d{1,3}\b",
        value,
    ):
        return IntentClass.SYSTEM_SETTING
    if "clipboard" in value or "copied text" in value or "what did i copy" in value:
        return IntentClass.QUERY
    if re.search(
        r"(?:^|\b)(?:is|check if|whether)\s+([\w.-]+(?:\s+[\w.-]+){0,3})\s+(?:is\s+)?(?:running|open|active)\b",
        value,
    ):
        return IntentClass.QUERY
    if any(term in value for term in (
        "wifi", "wi-fi", "wireless", "battery", "volume", "audio", "master audio",
        "ram", "memory", "cpu", "processor", "network", "internet",
    )):
        if any(term in value for term in (
            "status", "usage", "percentage", "percent", "connected", "connection",
            "running", "free", "available", "how much", "check", "show", "what is",
            "what's", "current", "remaining", "left",
        )) or value.startswith("is "):
            return IntentClass.QUERY
    if any(term in value for term in (
        "brightness", "settings", "setting", "night light", "focus assist", "bluetooth",
    )):
        return IntentClass.SYSTEM_SETTING
    if re.search(r"\b(open|launch|start|fire up|bring up)\b", value) or re.search(
        r"\brun\s+(?:notepad|calculator|paint|spotify|brave|chrome|edge|discord|visual studio code)\b",
        value,
    ):
        return IntentClass.LAUNCH
    if any(term in value for term in (
        "play music", "resume music", "continue playback", "start playback",
        "play spotify", "resume spotify", "pause music", "pause playback",
        "pause spotify", "stop music", "stop playback", "stop spotify playback",
        "next track", "next song", "skip this song", "previous track",
        "previous song", "skip back one track", "skip forward one track",
    )):
        return IntentClass.CONTROL
    if any(term in value for term in (
        "minimize", "maximize", "make this window full size", "make this app full screen",
        "expand the current window", "fill the screen with this window", "put this window away",
        "send the current window to the taskbar", "hide the foreground window",
        "restore", "unminimize", "bring this window back",
        "close window", "close this window", "close current window", "close current app",
        "close the current app", "close the foreground window", "exit this window",
        "shut this app window", "close it",
    )) or re.search(r"\bclose\s+(?:the\s+)?(?:current|this)\s+(?:window|app)\b", value) or re.match(r"^close\s+", value):
        return IntentClass.CONTROL
    if any(term in value for term in (
        "list ", "display ", "show ", "what ", "how ", "is ", "check ",
        "tell me ", "give me ", "whether ", "do i have ",
        "remaining charge", "battery percentage",
    )) or " running" in value or " active" in value:
        return IntentClass.QUERY
    return IntentClass.CHAT


class IntentRouter:
    """Rules-first registry retrieval with class filters and explicit hard negatives."""

    def __init__(self, registry: ActionRegistry | None = None, store=None) -> None:
        self.registry = registry or ActionRegistry()
        self.store = store

    def route(self, utterance: str) -> RouteResult:
        normalized = normalize(utterance)
        intent_class = classify(normalized)
        if not normalized:
            return RouteResult(
                status="clarify", normalized_text="", reason="empty_utterance",
                clarification="What would you like Prixon to do?",
            )

        candidates: list[Candidate] = []
        owner_aliases = self.store.aliases() if self.store is not None else []
        for action in self.registry.by_class(intent_class):
            action_aliases = [
                alias["phrase"] for alias in owner_aliases
                if alias["target_type"] == "action" and alias["target"] == action.name
            ]
            if (
                any(normalize(negative) == normalized for negative in action.hard_negatives)
                and not any(phrase in normalized for phrase in action_aliases)
            ):
                continue
            phrases = (action.name.replace(".", " "), *action.examples, *action_aliases)
            best = max((self._phrase_score(normalized, phrase) for phrase in phrases), default=0)
            if self.store is not None and best > 0:
                for negative in self.store.negative_examples():
                    if negative["action_name"] == action.name:
                        similarity = self._phrase_score(normalized, negative["phrase"])
                        if similarity >= 0.45:
                            best = max(0.0, best - (negative["penalty"] * similarity))
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
        if best.score < 0.42 or (len(candidates) > 1 and margin < 0.08):
            return RouteResult(
                status="clarify", normalized_text=normalized, intent_class=intent_class,
                candidates=candidates[:5], confidence=best.score,
                reason="low_match_or_ambiguous",
                clarification="Did you mean " + " or ".join(
                    candidate.action.description.lower() for candidate in candidates[:2]
                ) + "?",
            )
        if not self._has_required_slots(normalized, best.action.required_slots):
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
            return 0.0
        if text == target:
            return 1.0
        if re.search(r"(?<!\w)" + re.escape(target) + r"(?!\w)", text):
            return 0.92
        tokens = set(target.split())
        words = set(text.split())
        if not tokens:
            return 0.0
        return round((len(tokens & words) / len(tokens)) * 0.78, 4)

    @staticmethod
    def _has_required_slots(text: str, slots: tuple[str, ...]) -> bool:
        if not slots:
            return True
        if "application" in slots:
            return bool(
                re.search(r"\b(open|launch|start|fire up|bring up)\s+\w+", text)
            or re.search(
                r"\brun\s+(?:notepad|calculator|paint|spotify|brave|chrome|edge|discord|visual studio code)\b",
                text,
            )
                or re.search(
                    r"\b(?:is|check if|whether)\s+([\w.-]+(?:\s+[\w.-]+){0,3})\s+(?:is\s+)?(?:running|open|active)\b",
                    text,
                )
            )
        if "level" in slots:
            return bool(re.search(r"\b\d{1,3}\s*%?\b", text))
        if "window" in slots:
            return any(word in text for word in (
                "this window", "current window", "this app", "current app",
                "foreground", " it", "that",
            ))
        if "setting" in slots:
            return any(term in text for term in (
                "display", "screen", "sound", "audio", "wifi", "wi-fi",
                "bluetooth", "battery", "night light", "focus", "network",
            ))
        if "file" in slots:
            return any(token in text for token in ("file", "document", "this one", "selected"))
        return False
