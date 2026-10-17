from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IntentClass(StrEnum):
    QUERY = "query"
    CONTROL = "control"
    LAUNCH = "launch"
    FILE_OPERATION = "file_operation"
    SYSTEM_SETTING = "system_setting"
    CHAT = "chat"


class RiskTier(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    ROUTINE = "allowlisted_routine"
    ALWAYS_CONFIRM = "always_confirm"


class ActionSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    description: str
    examples: tuple[str, ...] = ()
    intent_class: IntentClass
    verb_type: str
    target_type: str
    required_slots: tuple[str, ...] = ()
    risk: RiskTier = RiskTier.READ_ONLY
    postconditions: tuple[str, ...] = ()
    undo_supported: bool = False


class Candidate(BaseModel):
    action: ActionSpec
    score: float = Field(ge=0, le=1)
    matched_by: str


class RouteResult(BaseModel):
    status: str
    normalized_text: str
    intent_class: IntentClass | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    selected_action: str | None = None
    confidence: float = 0
    reason: str
    requires_confirmation: bool = False
    clarification: str | None = None


class PlanStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    expected_outcome: str


class AgentPlan(BaseModel):
    goal: str
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


class PlanValidation(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class TeachAliasRequest(BaseModel):
    phrase: str = Field(min_length=2, max_length=100)
    action_name: str = Field(min_length=2, max_length=100)
    confirmed: bool = False
