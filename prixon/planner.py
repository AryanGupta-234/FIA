from __future__ import annotations

from prixon.registry import ActionRegistry
from prixon.schemas import AgentPlan, PlanValidation


def validate_plan(
    plan: AgentPlan, registry: ActionRegistry, max_steps: int = 8,
) -> PlanValidation:
    errors: list[str] = []
    if len(plan.steps) > max_steps:
        errors.append(f"step_budget_exceeded:{max_steps}")
    if len(plan.steps) == 0:
        errors.append("empty_plan")
    for index, step in enumerate(plan.steps):
        action = registry.get(step.tool)
        if action is None:
            errors.append(f"unknown_tool:{index}:{step.tool}")
            continue
        if len(set(step.depends_on)) != len(step.depends_on):
            errors.append(f"duplicate_dependency:{index}")
        for dependency in step.depends_on:
            if dependency < 0 or dependency >= index:
                errors.append(f"invalid_dependency:{index}:{dependency}")
        for slot in action.required_slots:
            if slot not in step.args or step.args[slot] in (None, ""):
                errors.append(f"required_slot_missing:{index}:{slot}")
        unknown_args = set(step.args) - set(action.parameter_schema)
        if unknown_args:
            errors.append(f"unknown_arguments:{index}:{','.join(sorted(unknown_args))}")
        if any(
            isinstance(value, str) and value.startswith("$previous.")
            for value in step.args.values()
        ) and (index == 0 or index - 1 not in step.depends_on):
            errors.append(f"previous_reference_without_dependency:{index}")
        if not step.expected_outcome.strip():
            errors.append(f"expected_outcome_missing:{index}")
        prohibited = {"command", "shell", "script", "powershell", "cmdline"}
        if prohibited.intersection(step.args):
            errors.append(f"arbitrary_command_argument:{index}")
    return PlanValidation(valid=not errors, errors=errors)
