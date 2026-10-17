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

    def teach_entity(
        self, phrase: str, entity_type: str, target: str,
        scope: dict | None = None,
    ) -> None:
        if entity_type not in {"application", "window", "folder", "file", "setting"}:
            raise ValueError("Unsupported entity alias type")
        self.store.put_alias(
            phrase, entity_type, target, scope=scope, confidence=1.0, explicit=True,
        )
        self.store.audit("entity_alias_explicitly_taught", {
            "phrase": phrase, "entity_type": entity_type, "target": target,
        })

    def correct(self, phrase: str, wrong_action: str, corrected_action: str) -> LearningResult:
        self.store.add_negative_example(phrase, wrong_action)
        self.store.put_alias(
            phrase, "action", corrected_action, confidence=0.9, explicit=False,
        )
        self.store.audit("owner_corrected_action", {
            "phrase": phrase, "wrong_action": wrong_action,
            "corrected_action": corrected_action,
        })
        return LearningResult("corrected", phrase, corrected_action, 0.9, 1)

    def observe(
        self, phrase: str, action_name: str, *, success: bool,
        session_id: str, risk: RiskTier, explicit: bool = False,
    ) -> LearningResult:
        if explicit and success:
            return self.teach(phrase, action_name)
        if not success:
            self.store.add_negative_example(phrase, action_name)
        stats = self.store.observe_alias(phrase, action_name, success, session_id)
        session_count = len(stats["sessions"])
        high_risk = risk == RiskTier.ALWAYS_CONFIRM
        if stats["confidence"] < 0.5:
            self.store.remove_alias(phrase)
            status = "demoted"
        elif stats["confidence"] >= self.promotion_threshold and session_count >= 3 and not high_risk:
            self.store.put_alias(
                phrase, "action", action_name, confidence=stats["confidence"], explicit=False,
            )
            status = "promoted"
        else:
            status = "candidate"
        self.store.audit("alias_learning_observation", {
            "phrase": stats["phrase"], "target": action_name, "success": success,
            "confidence": stats["confidence"], "session_count": session_count, "status": status,
        })
        return LearningResult(status, stats["phrase"], action_name, stats["confidence"], session_count)

    def promotion_candidates(self) -> list[dict]:
        candidates = []
        for row in self.store.alias_candidates():
            evidence = row["successes"] + row["failures"]
            confidence = (row["successes"] + 1) / (evidence + 2)
            sessions = len(row["sessions"])
            if confidence >= self.promotion_threshold and sessions >= 3:
                candidates.append({
                    "phrase": row["phrase"], "action_name": row["target"],
                    "confidence": confidence, "independent_sessions": sessions,
                    "successes": row["successes"], "failures": row["failures"],
                    "requires_owner_approval": True,
                })
        return sorted(candidates, key=lambda item: item["confidence"], reverse=True)

    def approve_candidate(
        self, phrase: str, action_name: str, risk: RiskTier,
    ) -> LearningResult:
        stats = next(
            (row for row in self.store.alias_candidates()
             if row["phrase"] == " ".join(phrase.casefold().split()) and row["target"] == action_name),
            None,
        )
        if stats is None:
            raise ValueError("Learning candidate was not found.")
        total = stats["successes"] + stats["failures"]
        confidence = (stats["successes"] + 1) / (total + 2)
        sessions = len(stats["sessions"])
        if confidence < self.promotion_threshold or sessions < 3:
            raise ValueError("Candidate has not met the promotion evidence threshold.")
        # This method is called only from the confirmation-gated owner approval endpoint.
        self.store.put_alias(
            phrase, "action", action_name, confidence=confidence, explicit=True,
        )
        self.store.remove_alias_candidate(phrase, action_name)
        self.store.audit("owner_approved_learning_candidate", {
            "phrase": phrase, "target": action_name, "confidence": confidence,
            "sessions": sessions, "risk": risk.value,
        })
        return LearningResult("promoted", phrase, action_name, confidence, sessions)

    def reject_candidate(self, phrase: str, action_name: str) -> bool:
        removed = self.store.remove_alias_candidate(phrase, action_name)
        self.store.add_negative_example(phrase, action_name)
        self.store.audit("owner_rejected_learning_candidate", {
            "phrase": phrase, "target": action_name,
        })
        return removed > 0

    def consolidate(self) -> dict[str, int]:
        decayed = 0
        demoted = 0
        import time
        now = time.time()
        for row in self.store.alias_candidates():
            elapsed_days = max(0.0, (now - row["last_updated"]) / 86400)
            factor = 0.5 ** (elapsed_days / 60.0)
            successes = row["successes"] * factor
            failures = row["failures"] * factor
            confidence = (successes + 1) / (successes + failures + 2)
            self.store.update_alias_candidate(
                row["phrase"], row["target"], successes, failures, row["sessions"], now,
            )
            decayed += 1
            if confidence < 0.5:
                self.store.remove_alias_if_implicit(row["phrase"])
                self.store.remove_alias_candidate(row["phrase"], row["target"])
                demoted += 1
        proposals = len(self.promotion_candidates())
        summary = {
            "candidates_decayed": decayed,
            "aliases_demoted": demoted,
            "promotion_proposals": proposals,
        }
        self.store.set_setting("learning.last_digest", summary)
        self.store.audit("lexicon_consolidated", summary)
        return summary

    def lookup(self, phrase: str) -> dict | None:
        return self.store.alias(phrase)
