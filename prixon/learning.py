from __future__ import annotations

from dataclasses import dataclass

from prixon.schemas import RiskTier
from prixon.store import AgentStore


@dataclass(frozen=True)
class LearningResult:
    status: str
    phrase: str
    target: str
    confidence: float
    sessions: int


class OwnerLexicon:
    """Learns only from owner-entered teaching, confirmations and explicit feedback."""

    def __init__(self, store: AgentStore, promotion_threshold: float = 0.85) -> None:
        self.store = store
        self.promotion_threshold = promotion_threshold

    def teach(self, phrase: str, action_name: str) -> LearningResult:
        self.store.put_alias(
            phrase, "action", action_name, confidence=1.0, explicit=True,
        )
        self.store.audit("alias_explicitly_taught", {"phrase": phrase, "target": action_name})
        return LearningResult("promoted", phrase, action_name, 1.0, 1)

    def observe(
        self,
        phrase: str,
        action_name: str,
        *,
        success: bool,
        session_id: str,
        risk: RiskTier,
        explicit: bool = False,
    ) -> LearningResult:
        if explicit and success:
            return self.teach(phrase, action_name)
        stats = self.store.observe_alias(phrase, action_name, success, session_id)
        session_count = len(stats["sessions"])
        high_risk = risk == RiskTier.ALWAYS_CONFIRM
        if stats["confidence"] < 0.5:
            self.store.remove_alias(phrase)
            status = "demoted"
        elif (
            stats["confidence"] >= self.promotion_threshold
            and session_count >= 3
            and not high_risk
        ):
            self.store.put_alias(
                phrase, "action", action_name,
                confidence=stats["confidence"], explicit=False,
            )
            status = "promoted"
        else:
            status = "candidate"
        self.store.audit("alias_learning_observation", {
            "phrase": stats["phrase"], "target": action_name,
            "success": success, "confidence": stats["confidence"],
            "session_count": session_count, "status": status,
        })
        return LearningResult(status, stats["phrase"], action_name, stats["confidence"], session_count)

    def lookup(self, phrase: str) -> dict | None:
        return self.store.alias(phrase)
