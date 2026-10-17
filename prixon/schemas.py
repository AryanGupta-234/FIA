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
    hard_negatives: tuple[str, ...] = ()
    intent_class: IntentClass
    verb_type: str
    target_type: str
    required_slots: tuple[str, ...] = ()
    parameter_schema: dict[str, str] = Field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    postconditions: tuple[str, ...] = ()
    risk: RiskTier = RiskTier.READ_ONLY
    undo_supported: bool = False
    automation_tiers: tuple[str, ...] = ("native_api",)


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
    slots: dict[str, Any] = Field(default_factory=dict)


class ThoughtRecord(BaseModel):
    observation: str
    hypothesis: str
    next_action: str
    expected_outcome: str


class PlanStep(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    expected_outcome: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AgentPlan(BaseModel):
    goal: str
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
    thought: ThoughtRecord | None = None


class PlanValidation(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


class DecisionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class RunRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    args: dict[str, Any] = Field(default_factory=dict)
    execute: bool = False
    confirmed: bool = False
    session_id: str = "local-session"


class TeachAliasRequest(BaseModel):
    phrase: str = Field(min_length=2, max_length=100)
    action_name: str = Field(min_length=2, max_length=100)
    confirmed: bool = False


class GoalCreateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    priority: int = Field(default=50, ge=0, le=100)
    plan: AgentPlan | None = None


class GoalStatusRequest(BaseModel):
    status: str


class AliasFeedbackRequest(BaseModel):
    phrase: str = Field(min_length=2, max_length=100)
    action_name: str = Field(min_length=2, max_length=100)
    success: bool
    corrected_action: str | None = Field(default=None, min_length=2, max_length=100)
    session_id: str = "local-session"


class ProactiveFeedbackRequest(BaseModel):
    trigger: str
    accepted: bool


class EntityAliasRequest(BaseModel):
    phrase: str = Field(min_length=2, max_length=100)
    entity_type: str
    target: str = Field(min_length=1, max_length=500)
    confirmed: bool = False


class MacroApprovalRequest(BaseModel):
    approved: bool = True


class MacroRunRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    execute: bool = False
    confirmed: bool = False


class UndoRequest(BaseModel):
    undo_id: str = Field(min_length=1, max_length=64)
