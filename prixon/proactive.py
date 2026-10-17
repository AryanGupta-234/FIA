from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from prixon.store import AgentStore


@dataclass(frozen=True)
class Suggestion:
    trigger: str
    title: str
    message: str
    created_at: float
    score: float


class ProactiveEngine:
    """Rules-first, suggest-only proactive layer with persistent annoyance and cooldowns."""

    def __init__(
        self, store: AgentStore, cooldown_seconds: int = 7200,
        max_interruptions_per_hour: int = 3, ignore_after_seconds: int = 900,
    ) -> None:
        self.store = store
        self.cooldown_seconds = cooldown_seconds
        self.max_interruptions_per_hour = max_interruptions_per_hour
        self.ignore_after_seconds = ignore_after_seconds
        self._last_trigger: dict[str, float] = store.get_setting("proactive.cooldowns", {})
        self._annoyance = float(store.get_setting("proactive.annoyance", 0.0))
        self._recent_suggestions: list[float] = store.get_setting("proactive.recent", [])
        self._pending: dict[str, float] = store.get_setting("proactive.pending", {})

    def evaluate(
        self, event_type: str, payload: dict[str, Any], *,
        focus_mode: bool = False, fullscreen: bool = False, now: float | None = None,
    ) -> Suggestion | None:
        now = now or time.time()
        self._expire_ignored(now)
        self._decay_annoyance(now)
        if focus_mode or fullscreen:
            return None
        if now - self._last_trigger.get(event_type, 0) < self.cooldown_seconds:
            return None
        self._recent_suggestions = [stamp for stamp in self._recent_suggestions if now - stamp < 3600]
        if self._annoyance >= 3 or len(self._recent_suggestions) >= self.max_interruptions_per_hour:
            self._persist()
            return None

        candidate: tuple[str, str] | None = None
        if event_type == "process_crashed":
            name = str(payload.get("name") or "An application")
            candidate = (
                f"{name} stopped unexpectedly",
                "An application appears to have crashed. Check the event before reopening it.",
            )
        elif event_type == "battery_low" and float(payload.get("percent", 100)) <= 20:
            candidate = (
                "Battery is low",
                "Battery is below 20%. Consider connecting power or enabling battery saver.",
            )
        elif event_type == "download_finished":
            candidate = (
                "Download finished",
                "A download appears to have completed. Review it when convenient.",
            )
        elif event_type == "routine_due":
            candidate = (
                str(payload.get("title") or "Routine reminder"),
                str(payload.get("message") or "A saved routine is due."),
            )
        if not candidate:
            return None

        self._last_trigger[event_type] = now
        self._recent_suggestions.append(now)
        self._pending[event_type] = now
        suggestion = Suggestion(
            trigger=event_type, title=candidate[0], message=candidate[1],
            created_at=now, score=max(0.0, 1.0 - self._annoyance * 0.2),
        )
        self.store.audit("proactive_suggestion", {
            "trigger": event_type, "title": suggestion.title,
            "message": suggestion.message, "score": suggestion.score,
        })
        self._persist()
        return suggestion

    def record_response(self, trigger: str, accepted: bool) -> None:
        self._pending.pop(trigger, None)
        if accepted:
            self._annoyance = max(0.0, self._annoyance - 1.0)
        else:
            self._annoyance = min(5.0, self._annoyance + 1.0)
        self.store.audit("proactive_feedback", {
            "trigger": trigger, "accepted": accepted, "annoyance": self._annoyance,
        })
        self._persist()

    def _expire_ignored(self, now: float) -> None:
        for trigger, created in list(self._pending.items()):
            if now - created >= self.ignore_after_seconds:
                self._pending.pop(trigger, None)
                self._annoyance = min(5.0, self._annoyance + 1.0)
                self.store.audit("proactive_ignored", {"trigger": trigger, "annoyance": self._annoyance})

    def _decay_annoyance(self, now: float) -> None:
        last = max(self._recent_suggestions, default=now)
        elapsed_hours = max(0.0, (now - last) / 3600)
        self._annoyance = max(0.0, self._annoyance - elapsed_hours / 24.0)

    def _persist(self) -> None:
        self.store.set_setting("proactive.annoyance", self._annoyance)
        self.store.set_setting("proactive.cooldowns", self._last_trigger)
        self.store.set_setting("proactive.recent", self._recent_suggestions)
        self.store.set_setting("proactive.pending", self._pending)
