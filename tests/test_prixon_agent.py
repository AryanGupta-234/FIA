from prixon.governance import decide
from prixon.planner import validate_plan
from prixon.registry import ActionRegistry
from prixon.router import IntentRouter
from prixon.schemas import AgentPlan, PlanStep, RiskTier


def test_status_query_routes_without_llm():
    result = IntentRouter().route("show system health")
    assert result.status == "selected"
    assert result.selected_action == "system.status"


def test_launch_without_target_asks_for_clarification():
    result = IntentRouter().route("open")
    assert result.status in {"unresolved", "clarify"}


def test_launch_with_target_selects_registered_action():
    result = IntentRouter().route("open notepad")
    assert result.status == "selected"
    assert result.selected_action == "app.launch"


def test_file_operation_is_never_auto_approved():
    decision = decide(RiskTier.ALWAYS_CONFIRM)
    assert not decision.allowed
    assert decision.requires_confirmation
    assert decision.autonomy_level == "L0"


def test_file_operation_requires_explicit_confirmation():
    decision = decide(RiskTier.ALWAYS_CONFIRM, confirmed=True)
    assert decision.allowed
    assert decision.requires_confirmation


def test_planner_rejects_unknown_tools_and_forward_dependencies():
    plan = AgentPlan(
        goal="test",
        steps=[
            PlanStep(tool="unknown.command", args={}, expected_outcome="done"),
            PlanStep(tool="system.status", depends_on=[2], expected_outcome="done"),
        ],
    )
    result = validate_plan(plan, ActionRegistry())
    assert not result.valid
    assert any(error.startswith("unknown_tool") for error in result.errors)
    assert any(error.startswith("invalid_dependency") for error in result.errors)


def test_planner_accepts_registered_read_only_tool():
    plan = AgentPlan(
        goal="check status",
        steps=[PlanStep(tool="system.status", expected_outcome="status_snapshot_returned")],
    )
    assert validate_plan(plan, ActionRegistry()).valid
