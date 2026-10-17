from __future__ import annotations

from prixon.registry import ActionRegistry
from prixon.schemas import AgentPlan, PlanValidation


def validate_plan(plan: AgentPlan, registry: ActionRegistry, max_steps: int = 8) -> PlanValidation:
    errors: list[str] = []
    if len(plan.steps) > max_steps:
        errors.append(f"step_budget_exceeded:{max_steps}")
    for index, step in enumerate(plan.steps):
        if registry.get(step.tool) is None:
            errors.append(f"unknown_tool:{index}:{step.tool}")
        for dependency in step.depends_on:
            if dependency < 0 or dependency >= index:
                errors.append(f"invalid_dependency:{index}:{dependency}")
    return PlanValidation(valid=not errors, errors=errors)
