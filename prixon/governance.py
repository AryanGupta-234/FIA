from __future__ import annotations

from dataclasses import dataclass

from prixon.schemas import RiskTier


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_confirmation: bool
    autonomy_level: str
    reason: str


def decide(risk: RiskTier, *, confirmed: bool = False, allowlisted: bool = False) -> Decision:
    if risk == RiskTier.READ_ONLY:
        return Decision(True, False, "L1", "read_only_action")
    if risk == RiskTier.REVERSIBLE:
        return Decision(True, False, "L2", "reversible_action_with_undo")
    if risk == RiskTier.ROUTINE:
        if allowlisted:
            return Decision(True, False, "L3", "owner_approved_allowlisted_routine")
        return Decision(False, True, "L0", "routine_not_allowlisted")
    if confirmed:
        return Decision(True, True, "L4", "explicit_confirmation_received")
    return Decision(False, True, "L0", "explicit_confirmation_required")
