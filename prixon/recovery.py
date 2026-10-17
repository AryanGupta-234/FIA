from __future__ import annotations

from dataclasses import dataclass

from prixon.schemas import AgentPlan, PlanStep


@dataclass(frozen=True)
class PartialRecovery:
    plan: AgentPlan | None
    failed_index: int | None
    resumed_indices: tuple[int, ...]
    blocked_indices: tuple[int, ...]
    reason: str


def build_partial_recovery_plan(
    original: AgentPlan,
    execution: dict,
) -> PartialRecovery:
    """Build a suffix plan excluding completed/failed steps and failed dependencies.

    Only independent, not-yet-attempted steps are resumed. The failed action is never
    repeated. Dependencies on the successful prefix are treated as already satisfied.
    """
    if execution.get("status") != "failed":
        return PartialRecovery(None, None, (), (), "execution_not_retryable")

    results = execution.get("steps") or []
    failed = next((item for item in results if not item.get("success")), None)
    if failed is None:
        return PartialRecovery(None, None, (), (), "failed_step_result_missing")

    try:
        failed_index = int(failed["index"])
    except (KeyError, TypeError, ValueError):
        return PartialRecovery(None, None, (), (), "failed_step_index_invalid")

    if failed_index < 0 or failed_index >= len(original.steps):
        return PartialRecovery(None, None, (), (), "failed_step_index_out_of_range")

    successful_prefix: dict[int, dict] = {}
    for item in results:
        try:
            index = int(item["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if index < failed_index and item.get("success"):
            successful_prefix[index] = item

    if any(index not in successful_prefix for index in range(failed_index)):
        return PartialRecovery(
            None, failed_index, (), (), "execution_prefix_not_fully_verified",
        )

    blocked = {failed_index}
    blocked_order: list[int] = []
    old_to_new: dict[int, int] = {}
    resumed: list[PlanStep] = []
    resumed_indices: list[int] = []

    for original_index in range(failed_index + 1, len(original.steps)):
        step = original.steps[original_index]
        blocked_by_dependency = any(
            dependency in blocked
            or (
                dependency >= failed_index
                and dependency not in old_to_new
            )
            or (
                dependency < failed_index
                and dependency not in successful_prefix
            )
            for dependency in step.depends_on
        )

        previous_reference_missing = any(
            isinstance(value, str)
            and value.startswith("$previous.")
            and original_index - 1 not in old_to_new
            for value in step.args.values()
        )

        if blocked_by_dependency or previous_reference_missing:
            blocked.add(original_index)
            blocked_order.append(original_index)
            continue

        rebased_dependencies = [
            old_to_new[dependency]
            for dependency in step.depends_on
            if dependency >= failed_index
        ]
        old_to_new[original_index] = len(resumed)
        resumed_indices.append(original_index)
        resumed.append(PlanStep(
            tool=step.tool,
            args=dict(step.args),
            depends_on=rebased_dependencies,
            expected_outcome=step.expected_outcome,
            confidence=step.confidence,
        ))

    if not resumed:
        return PartialRecovery(
            None, failed_index, (), tuple(blocked_order),
            "no_independent_remaining_steps",
        )

    return PartialRecovery(
        AgentPlan(goal=f"{original.goal} (safe partial recovery)", steps=resumed),
        failed_index,
        tuple(resumed_indices),
        tuple(blocked_order),
        "independent_steps_available",
    )
