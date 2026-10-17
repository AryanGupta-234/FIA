from __future__ import annotations

import time

import pytest

from prixon.confidence import (
    DecisionSignals,
    fit_logistic_weights,
    fuse_confidence,
    meets_risk_threshold,
)
from prixon.entities import EntityIndex, ReferenceResolver
from prixon.events import EventBus
from prixon.executor import ActionExecutor
from prixon.governance import decide
from prixon.kill_switch import KillSwitch
from prixon.learning import OwnerLexicon
from prixon.ollama import OllamaClient
from prixon.planner import validate_plan
from prixon.proactive import ProactiveEngine
from prixon.registry import ActionRegistry
from prixon.router import IntentRouter
from prixon.runtime import AgentRuntime
from prixon.schemas import AgentPlan, PlanStep, RiskTier
from prixon.store import AgentStore


@pytest.fixture
def store(tmp_path):
    return AgentStore(tmp_path / "prixon-test.sqlite3")


def test_entity_alias_is_exact_and_grounded(store):
    index = EntityIndex(store)
    index.refresh("application", [
        {"name": "Spotify", "target": r"C:\Users\test\Start Menu\Spotify.lnk"},
    ])
    store.put_alias("music thing", "application", r"C:\Users\test\Start Menu\Spotify.lnk", explicit=True)
    result = index.resolve("music thing", "application")
    assert result is not None
    assert result["matched_by"] == "owner_alias"
    assert result["target"].endswith("Spotify.lnk")


def test_entity_resolver_rejects_ambiguous_names(store):
    index = EntityIndex(store)
    index.refresh("application", [
        {"name": "Microsoft Edge", "target": r"C:\Apps\Edge\edge.lnk"},
        {"name": "Microsoft Excel", "target": r"C:\Apps\Excel\excel.lnk"},
    ])
    assert index.resolve("Microsoft", "application") is None


def test_reference_memory_expires():
    resolver = ReferenceResolver(idle_seconds=60)
    resolver.remember({"kind": "window", "name": "Notepad", "hwnd": 123})
    assert resolver.resolve("it")["hwnd"] == 123
    expiring = ReferenceResolver(idle_seconds=0)
    expiring.remember({"kind": "window", "name": "Notepad", "hwnd": 123})
    time.sleep(0.001)
    assert expiring.resolve("it") is None


def test_owner_synonym_promotes_after_confident_multi_session_evidence(store):
    lexicon = OwnerLexicon(store)
    sessions = ["session-a", "session-b", "session-c", "session-a", "session-b"]
    for session in sessions:
        result = lexicon.observe(
            "fire up", "app.launch", success=True, session_id=session,
            risk=RiskTier.REVERSIBLE,
        )
    assert result.status == "promotion_ready"
    assert result.confidence >= 0.85
    assert result.sessions == 3
    assert lexicon.lookup("fire up") is None
    approved = lexicon.approve_candidate("fire up", "app.launch", RiskTier.REVERSIBLE)
    assert approved.status == "promoted"
    assert lexicon.lookup("fire up")["target"] == "app.launch"


def test_implicit_learning_never_promotes_always_confirm_action(store):
    lexicon = OwnerLexicon(store)
    for session in ["a", "b", "c", "a", "b", "c"]:
        result = lexicon.observe(
            "remove this permanently", "file.quarantine", success=True,
            session_id=session, risk=RiskTier.ALWAYS_CONFIRM,
        )
    assert result.status == "candidate"
    assert lexicon.lookup("remove this permanently") is None


def test_explicit_owner_teaching_can_promote_immediately(store):
    result = OwnerLexicon(store).teach("fire up", "app.launch")
    assert result.status == "promoted"
    assert result.confidence == 1.0


def test_nightly_lexicon_consolidation_decays_candidate_evidence(store):
    store.observe_alias("maybe this", "app.launch", False, "session-a")
    result = OwnerLexicon(store).consolidate()
    assert result["candidates_decayed"] == 1


def test_confidence_fusion_and_risk_thresholds():
    signals = DecisionSignals(
        retrieval_margin=1, slot_grounding=1, llm_confidence=1,
        context_prior=1, user_lexicon_hit=1,
    )
    assert fuse_confidence(signals) == 1.0
    assert meets_risk_threshold(0.8, "reversible")
    assert not meets_risk_threshold(1.0, "always_confirm")


def test_logistic_weight_fit_requires_labeled_data_and_nonnegative_output():
    rows = [
        (DecisionSignals(1, 1, 0.2, 0.8, 0.1), 1 if index >= 10 else 0)
        for index in range(20)
    ]
    weights = fit_logistic_weights(rows, epochs=30)
    assert set(weights) == {
        "retrieval_margin", "slot_grounding", "llm_confidence",
        "context_prior", "user_lexicon_hit",
    }
    assert all(value >= 0 for value in weights.values())
    with pytest.raises(ValueError):
        fit_logistic_weights(rows[:10])


def test_risk_gate_requires_confirmation_for_irreversible_action():
    denied = decide(RiskTier.ALWAYS_CONFIRM)
    allowed = decide(RiskTier.ALWAYS_CONFIRM, confirmed=True)
    assert not denied.allowed and denied.requires_confirmation
    assert allowed.allowed


def test_action_executor_rejects_arbitrary_shell_fields(store):
    registry = ActionRegistry()
    executor = ActionExecutor(registry, store, kill_switch=KillSwitch())
    try:
        result = executor.execute_action("system.status", {"shell": "whoami"})
        assert not result.success
        assert result.error == "arbitrary_command_arguments_rejected"
    finally:
        executor.shutdown()


def test_action_executor_blocks_l4_before_calling_windows_adapter(store):
    registry = ActionRegistry()
    executor = ActionExecutor(registry, store, kill_switch=KillSwitch())
    try:
        result = executor.execute_action(
            "file.quarantine", {"file": r"C:\Users\test\Desktop\report.txt"},
            confirmed=False, confidence=1.0,
        )
        assert not result.success
        assert result.error == "explicit_confirmation_required"
    finally:
        executor.shutdown()


def test_executor_stops_immediately_when_kill_switch_is_active(store):
    registry = ActionRegistry()
    kill = KillSwitch()
    kill.trigger("test")
    executor = ActionExecutor(registry, store, kill_switch=kill)
    try:
        result = executor.execute_action("system.status", {}, confidence=1.0)
        assert result.error == "kill_switch_active"
    finally:
        executor.shutdown()


def test_plan_validator_rejects_unknown_parameters_and_bad_references():
    registry = ActionRegistry()
    plan = AgentPlan(
        goal="unsafe plan",
        steps=[
            PlanStep(tool="system.status", args={"command": "calc"}, expected_outcome="status"),
            PlanStep(
                tool="window.maximize",
                args={"window": "$previous.window", "hwnd": "$previous.hwnd"},
                depends_on=[],
                expected_outcome="maximized",
            ),
        ],
    )
    result = validate_plan(plan, registry)
    assert not result.valid
    assert any(error.startswith("unknown_arguments") for error in result.errors)
    assert any(error.startswith("previous_reference_without_dependency") for error in result.errors)


def test_macro_evidence_is_idempotent_across_consolidation_runs(store):
    plan = {"goal": "routine", "steps": [{"tool": "system.status", "args": {}}]}
    store.record_macro("shape", "Routine", plan, "check my pc", evidence_count=4)
    store.record_macro("shape", "Routine", plan, "check my pc", evidence_count=4)
    macro = store.macros()[0]
    assert macro["successes"] == 4


def test_event_bus_preserves_order_and_drains_bounded_batches():
    bus = EventBus(max_queue=10)
    bus.publish("foreground_changed", {"hwnd": 10})
    bus.publish("process_started", {"pid": 42})
    items = bus.drain(1)
    assert len(items) == 1 and items[0].event_type == "foreground_changed"
    assert bus.drain()[0].event_type == "process_started"


def test_proactive_engine_obeys_focus_cooldown_and_annoyance(store):
    engine = ProactiveEngine(store, cooldown_seconds=3600)
    assert engine.evaluate("battery_low", {"percent": 15}, focus_mode=True, now=10000) is None
    first = engine.evaluate("battery_low", {"percent": 15}, now=10000)
    assert first is not None
    assert engine.evaluate("battery_low", {"percent": 12}, now=10030) is None
    engine.record_response("battery_low", accepted=False)
    assert store.get_setting("proactive.annoyance", 0) == 1.0


def test_ollama_client_rejects_non_loopback_endpoints():
    with pytest.raises(ValueError):
        OllamaClient("https://example.com")
    with pytest.raises(ValueError):
        OllamaClient("http://192.168.1.25:11434")
    assert OllamaClient("http://127.0.0.1:11434").base_url == "http://127.0.0.1:11434"


def test_intent_router_distinguishes_process_list_from_app_running():
    router = IntentRouter()
    assert router.route("list running processes").selected_action == "process.list"
    assert router.route("is spotify running").selected_action == "app.is_running"


def test_intent_router_asks_for_missing_launch_entity():
    result = IntentRouter().route("open")
    assert result.status in {"clarify", "unresolved"}


def test_negative_memory_penalizes_previously_corrected_intent(store):
    store.add_negative_example("is spotify running", "app.is_running", penalty_delta=0.75)
    result = IntentRouter(ActionRegistry(), store).route("is spotify running")
    assert result.selected_action != "app.is_running"


def test_explicit_correction_creates_positive_alias_and_negative_example(store):
    lexicon = OwnerLexicon(store)
    corrected = lexicon.correct("check spotify", "process.list", "app.is_running")
    assert corrected.status == "corrected"
    assert store.alias("check spotify")["target"] == "app.is_running"
    assert store.negative_examples()[0]["action_name"] == "process.list"


def test_reflex_queries_cover_ram_battery_wifi_and_cpu():
    router = IntentRouter()
    assert router.route("show RAM usage").selected_action == "system.memory"
    assert router.route("check battery").selected_action == "system.battery"
    assert router.route("is wifi connected").selected_action == "system.wifi"
    assert router.route("show cpu load").selected_action == "system.cpu"


def test_volume_control_phrase_is_not_misclassified_as_a_query():
    router = IntentRouter()
    assert router.route("turn volume down to 20").selected_action == "volume.set"
    assert router.route("volume at 50").selected_action == "volume.set"


def test_learning_signal_waits_for_delayed_owner_success(store):
    signal_id = store.queue_learning_signal(
        "fire up notepad", "app.launch", "session-a", "reversible", "undo-id",
    )
    pending = store.pending_learning_signals()
    assert len(pending) == 1 and pending[0]["id"] == signal_id
    store.discard_pending_learning(undo_id="undo-id")
    assert store.pending_learning_signals() == []


def test_learning_reset_removes_macros_and_pending_signals(store):
    store.record_macro("shape", "Routine", {"steps": []}, "do routine")
    store.queue_learning_signal("open app", "app.launch", "session", "reversible")
    removed = store.remove_all_user_learning()
    assert removed["macros"] == 1
    assert removed["pending_learning"] == 1
    assert store.pending_learning_signals() == []


def test_close_window_verb_routes_to_control_class():
    result = IntentRouter().route("please close this window")
    assert result.selected_action == "window.close"


def test_read_only_queries_execute_without_an_execute_flag(store):
    import asyncio

    from prixon.runtime import AgentRuntime

    runtime = AgentRuntime(store=store)
    try:
        result = asyncio.run(runtime.run_request("show RAM usage"))
        assert result["status"] == "completed"
        assert "RAM usage" in result["answer"]
    finally:
        runtime.executor.shutdown()


def test_check_if_application_is_running_accepts_the_grammar():
    router = IntentRouter()
    assert router.route("check if chrome is running").selected_action == "app.is_running"
    assert router.route("is discord open").selected_action == "app.is_running"


def test_unrelated_followup_does_not_erase_pending_learning(store):
    from prixon.runtime import AgentRuntime

    runtime = AgentRuntime(store=store)
    try:
        store.queue_learning_signal("show RAM usage", "system.memory", "session-x", "read_only")
        assert runtime._discard_rephrased_pending_learning("show CPU usage", "session-x") == 0
        assert len(store.pending_learning_signals()) == 1
    finally:
        runtime.executor.shutdown()


def test_explicit_rephrase_cancels_pending_learning_and_adds_negative(store):
    from prixon.runtime import AgentRuntime

    runtime = AgentRuntime(store=store)
    try:
        store.queue_learning_signal("open notepad", "app.launch", "session-x", "reversible")
        assert runtime._discard_rephrased_pending_learning("no, I meant calculator", "session-x") == 1
        assert store.pending_learning_signals() == []
        assert store.negative_examples()[0]["action_name"] == "app.launch"
    finally:
        runtime.executor.shutdown()


def test_rules_handle_additional_lookalikes_and_phrasings():
    router = IntentRouter()
    assert router.route("is notepad open").selected_action == "app.is_running"
    assert router.route("give me a pc health summary").selected_action == "system.status"
    assert router.route("display the process list").selected_action == "process.list"
    assert router.route("make this window full size").selected_action == "window.maximize"
    assert router.route("unminimize this window").selected_action == "window.restore"
    assert router.route("close the current app").selected_action == "window.close"


def test_polite_prefixes_do_not_change_query_or_control_class():
    router = IntentRouter()
    assert router.route("please is notepad open").selected_action == "app.is_running"
    assert router.route("please close the current app").selected_action == "window.close"
    assert router.route("current audio level").selected_action == "system.audio"
    assert router.route("please unminimize this window").selected_action == "window.restore"


def test_persisted_events_can_be_replayed_without_creating_duplicate_rows(store):
    from prixon.events import EventBus

    event_id = store.enqueue_event("download_finished", {"name": "sample.zip"})
    persisted = store.pending_events()
    bus = EventBus()
    bus.publish(
        persisted[0]["event_type"], persisted[0]["payload"],
        persisted_id=persisted[0]["id"],
    )
    event = bus.drain()[0]
    assert event.persisted_id == event_id
    assert event.event_type == "download_finished"
    assert store.pending_events()[0]["id"] == event_id


def test_active_goals_are_marked_interrupted_not_replayed(store):
    from prixon.agent_loop import AgentLoop
    from prixon.runtime import AgentRuntime

    runtime = AgentRuntime(store=store)
    goal_id = store.add_goal("interrupted test goal")
    store.set_goal_status(goal_id, "active")
    loop = AgentLoop(runtime)
    try:
        assert loop.recover_interrupted_goals() == 1
        assert store.goals(("blocked",))[0]["id"] == goal_id
    finally:
        runtime.executor.shutdown()


def test_executor_falls_back_from_native_to_ui_automation_and_verifies(tmp_path):
    class FakeAdapters:
        def capture_before(self, action, args):
            return {"hwnd": args["hwnd"], "iconic": False, "zoomed": False}

        def execute_tier(self, action, args, tier):
            if tier == "native_api":
                return {"hwnd": args["hwnd"], "iconic": False, "zoomed": False}
            if tier == "ui_automation":
                return {"hwnd": args["hwnd"], "iconic": False, "zoomed": True}
            raise AssertionError(f"Unexpected tier: {tier}")

        def undo(self, action, args, before, output):
            return True

    store = AgentStore(tmp_path / "fallback.sqlite3")
    registry = ActionRegistry()
    executor = ActionExecutor(
        registry, store, adapters=FakeAdapters(), kill_switch=KillSwitch(),
    )
    try:
        result = executor.execute_action(
            "window.maximize", {"window": "Editor", "hwnd": 1001}, confidence=1.0,
        )
        assert result.success
        assert result.verified
        assert result.output["automation_tier"] == "ui_automation"
    finally:
        executor.shutdown()


def test_executor_does_not_continue_fallback_after_timeout(tmp_path):
    class FakeAdapters:
        def capture_before(self, action, args):
            return {}

        def execute_tier(self, action, args, tier):
            raise TimeoutError("simulate worker timeout")

        def undo(self, action, args, before, output):
            return False

    from prixon.executor import ExecutionBudget

    store = AgentStore(tmp_path / "fallback-timeout.sqlite3")
    executor = ActionExecutor(
        ActionRegistry(), store, adapters=FakeAdapters(), kill_switch=KillSwitch(),
        budget=ExecutionBudget(step_timeout_seconds=0.01),
    )
    try:
        result = executor.execute_action(
            "window.maximize", {"window": "Editor", "hwnd": 1001}, confidence=1.0,
        )
        assert not result.success
        assert result.error is not None
        assert "timeout" in result.error
    finally:
        executor.shutdown()


def test_routine_store_claims_due_once_per_local_day(tmp_path):
    from datetime import datetime

    store = AgentStore(tmp_path / "routine.sqlite3")
    routine_id = store.create_routine(
        "Morning focus", 7, "08:30", weekdays=[0, 1, 2, 3, 4],
    )
    due = datetime(2026, 10, 19, 9, 0).astimezone()
    assert any(item["id"] == routine_id for item in store.due_routines(due))
    assert store.due_routines(due) == []


def test_routine_store_does_not_fire_on_unscheduled_weekday(tmp_path):
    from datetime import datetime

    store = AgentStore(tmp_path / "routine-days.sqlite3")
    routine_id = store.create_routine("Weekday only", 8, "08:00", weekdays=[0, 1, 2, 3, 4])
    saturday = datetime(2026, 10, 17, 9, 0).astimezone()
    assert routine_id not in [item["id"] for item in store.due_routines(saturday)]


def test_wmi_process_stop_classifier_marks_nonzero_exit_as_crash():
    from prixon.events import WinProcessTerminationObserver

    event_type, payload = WinProcessTerminationObserver.classify_stop("app.exe", 42, 1)
    assert event_type == "process_crashed"
    assert payload["unexpected"] is True
    normal_type, _ = WinProcessTerminationObserver.classify_stop("app.exe", 42, 0)
    assert normal_type == "process_stopped"


def test_router_routes_system_telemetry_queries_separately_from_settings():
    router = IntentRouter(ActionRegistry())
    assert router.route("is wifi connected").selected_action == "system.wifi"
    assert router.route("check battery").selected_action == "system.battery"
    assert router.route("check volume").selected_action == "system.audio"
    assert router.route("set volume to 30").selected_action == "volume.set"


def test_implicit_learning_waits_for_owner_approval(tmp_path):
    store = AgentStore(tmp_path / "owner-approval.sqlite3")
    lexicon = OwnerLexicon(store)
    for session in ("one", "two", "three", "one", "two"):
        result = lexicon.observe(
            "fire up", "app.launch", success=True,
            session_id=session, risk=RiskTier.REVERSIBLE,
        )
    assert result.status == "promotion_ready"
    assert lexicon.lookup("fire up") is None
    approved = lexicon.approve_candidate("fire up", "app.launch", RiskTier.REVERSIBLE)
    assert approved.status == "promoted"
    assert lexicon.lookup("fire up")["explicit"] is True


def test_entity_alias_to_deleted_file_is_rejected(tmp_path):
    from pathlib import Path

    store = AgentStore(tmp_path / "stale-alias.sqlite3")
    missing = tmp_path / "vanished.txt"
    store.put_alias("old report", "file", str(missing), explicit=True)
    result = EntityIndex(store).resolve("old report", "file")
    assert result is None
    assert any(row["event_type"] == "stale_entity_alias" for row in store.audit_rows())


def test_routine_due_event_is_persisted_with_the_routine_claim(tmp_path):
    from datetime import datetime

    store = AgentStore(tmp_path / "routine-event.sqlite3")
    routine_id = store.create_routine("Daily summary", 42, "08:00", weekdays=[0, 1, 2, 3, 4, 5, 6])
    due = datetime(2026, 10, 19, 9, 0).astimezone()
    fired = store.due_routines(due)
    assert fired[0]["id"] == routine_id
    pending = store.pending_events()
    assert pending[-1]["event_type"] == "routine_due"
    assert pending[-1]["payload"]["routine_id"] == routine_id


def test_successful_implicit_alias_never_auto_activates(tmp_path):
    store = AgentStore(tmp_path / "implicit-review.sqlite3")
    lexicon = OwnerLexicon(store)
    for session in ("session-a", "session-b", "session-c", "session-a", "session-b"):
        result = lexicon.observe(
            "open my editor", "app.launch", success=True,
            session_id=session, risk=RiskTier.REVERSIBLE,
        )
    assert result.status == "promotion_ready"
    assert store.alias("open my editor") is None
    assert len(lexicon.promotion_candidates()) == 1
    approved = lexicon.approve_candidate(
        "open my editor", "app.launch", RiskTier.REVERSIBLE,
    )
    assert approved.status == "promoted"
    assert store.alias("open my editor")["explicit"] is True


def test_run_endpoint_preview_never_executes_read_only_action(tmp_path):
    import asyncio

    class FakePerception:
        def snapshot(self):
            return {
                "platform": "test", "is_windows": False, "captured_at": 1,
                "cpu_percent": 5, "memory": {"total_bytes": 100, "available_bytes": 50, "percent": 50},
                "battery": None, "network": {}, "foreground_window": None, "process_count": 2,
            }
        def processes(self, limit=100):
            return []
        def installed_apps(self):
            return []
        def known_folders(self):
            return []
        def recent_files(self, limit=100):
            return []

    class FakeOllama:
        last_metrics = {}
        model = "test"
        async def health(self):
            return {"available": False}

    store = AgentStore(tmp_path / "preview-only.sqlite3")
    runtime = AgentRuntime(
        store=store, perception=FakePerception(), ollama=FakeOllama(),
    )
    called = []
    runtime.executor.execute_action = lambda *args, **kwargs: called.append(args) or None
    try:
        result = asyncio.run(runtime.run_request("check battery", execute=False))
        assert result["status"] == "selected"
        assert result["plan"]["steps"][0]["tool"] == "system.battery"
        assert called == []
    finally:
        runtime.executor.shutdown()


def test_router_application_slot_and_level_slot_require_valid_values():
    router = IntentRouter(ActionRegistry())
    assert router.route("open calculator").selected_action == "app.launch"
    assert router.route("set volume to 30").selected_action == "volume.set"
    assert router.route("set volume to 250").selected_action == "volume.set"


def test_volume_slot_values_are_validated_during_grounding(tmp_path):
    class FakePerception:
        def snapshot(self):
            return {
                "platform": "test", "is_windows": False, "captured_at": 1,
                "cpu_percent": 5, "memory": {"total_bytes": 100, "available_bytes": 50, "percent": 50},
                "battery": None, "network": {}, "foreground_window": None, "process_count": 2,
            }
        def processes(self, limit=100):
            return []
        def installed_apps(self):
            return []
        def known_folders(self):
            return []
        def recent_files(self, limit=100):
            return []

    class FakeOllama:
        last_metrics = {}
        model = "test"

    runtime = AgentRuntime(
        store=AgentStore(tmp_path / "volume-slot.sqlite3"),
        perception=FakePerception(),
        ollama=FakeOllama(),
    )
    try:
        args, error = runtime._fill_args(
            "volume.set", "set volume to 250", {"level": 250},
        )
        assert args["level"] == 250
        assert error == "Volume level must be between 0 and 100."
    finally:
        runtime.executor.shutdown()
