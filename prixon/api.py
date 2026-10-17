from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response

from prixon.agent_loop import AgentLoop
from prixon.governance import decide
from prixon.planner import validate_plan
from prixon.runtime import AgentRuntime
from prixon.ui import render_prixon_ui
from prixon.schemas import (
    AgentPlan,
    AliasFeedbackRequest,
    DecisionRequest,
    DeleteAliasRequest,
    EntityAliasRequest,
    GoalCreateRequest,
    GoalStatusRequest,
    LearningCandidateRequest,
    MacroApprovalRequest,
    MacroRunRequest,
    ProactiveFeedbackRequest,
    ResetLearningRequest,
    RiskTier,
    RoutineCreateRequest,
    RoutineStatusRequest,
    RunRequest,
    TeachAliasRequest,
)

router = APIRouter(prefix="/api/v1/agent", tags=["Prixon Agent"])

# One local agent runtime per API process. The runtime owns SQLite and local Ollama only.
runtime = AgentRuntime()
agent_loop = AgentLoop(runtime)


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def prixon_ui() -> HTMLResponse:
    return render_prixon_ui()


@router.get("/health")
async def agent_health() -> dict[str, Any]:
    model_status = await runtime.ollama.health()
    return {
        "agent": "Prixon",
        "status": "running" if agent_loop.running else "ready",
        "mode": "local_only",
        "platform": os.name,
        "ollama": model_status,
        "registered_actions": len(runtime.registry.all()),
        "semantic_retrieval": runtime.semantic is not None,
        "browser_debug": {
            "enabled": runtime.settings.browser_debug_enabled,
            "port": runtime.settings.browser_debug_port,
            "mode": "loopback_metadata_only",
        },
        "loop_running": agent_loop.running,
        "kill_switch_active": runtime.kill_switch.active,
        "execution_enabled": True,
        "scope": "local Windows actions only; no hosted model fallback",
    }


@router.get("/actions")
def list_actions() -> list[dict[str, Any]]:
    runtime._register_approved_macros()
    return [action.model_dump(mode="json") for action in runtime.registry.all()]


@router.post("/decide")
async def decide_intent(payload: DecisionRequest) -> dict[str, Any]:
    """Return the best grounded decision without performing any Windows action."""
    return await runtime.preview(payload.text)


@router.post("/run")
async def run_agent_request(payload: RunRequest) -> dict[str, Any]:
    return await runtime.run_request(
        payload.text,
        payload.args,
        execute=payload.execute,
        confirmed=payload.confirmed,
        session_id=payload.session_id,
    )


@router.post("/aliases")
def teach_action_alias(payload: TeachAliasRequest) -> dict[str, Any]:
    if not payload.confirmed:
        return {
            "status": "pending_confirmation",
            "phrase": payload.phrase,
            "action": payload.action_name,
            "message": "Explicit owner confirmation is required to teach a permanent mapping.",
        }
    action = runtime.registry.get(payload.action_name)
    if action is None:
        raise HTTPException(404, "Unknown registered action.")
    result = runtime.lexicon.teach(payload.phrase, payload.action_name)
    return {
        "status": result.status,
        "phrase": result.phrase,
        "action": result.target,
        "confidence": result.confidence,
    }


@router.post("/entities/aliases")
def teach_entity_alias(payload: EntityAliasRequest) -> dict[str, Any]:
    if not payload.confirmed:
        return {
            "status": "pending_confirmation",
            "phrase": payload.phrase,
            "entity_type": payload.entity_type,
            "target": payload.target,
        }
    try:
        runtime.lexicon.teach_entity(
            payload.phrase, payload.entity_type, payload.target, payload.scope,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"status": "learned", "phrase": payload.phrase, "entity_type": payload.entity_type}


@router.post("/learning/feedback")
def record_owner_feedback(payload: AliasFeedbackRequest) -> dict[str, Any]:
    action = runtime.registry.get(payload.action_name)
    if action is None:
        raise HTTPException(404, "Unknown registered action.")
    if payload.corrected_action:
        corrected = runtime.registry.get(payload.corrected_action)
        if corrected is None:
            raise HTTPException(404, "Unknown corrected action.")
        result = runtime.lexicon.correct(
            payload.phrase, payload.action_name, payload.corrected_action,
        )
    else:
        result = runtime.lexicon.observe(
            payload.phrase,
            payload.action_name,
            success=payload.success,
            session_id=payload.session_id,
            risk=action.risk,
            explicit=False,
        )
    return {
        "status": result.status,
        "phrase": result.phrase,
        "action": result.target,
        "confidence": result.confidence,
        "independent_sessions": result.sessions,
    }


@router.delete("/learning/aliases")
def delete_learning_alias(payload: DeleteAliasRequest) -> dict[str, Any]:
    runtime.store.remove_alias(payload.phrase)
    removed_candidates = runtime.store.remove_alias_candidate(payload.phrase, payload.target)
    runtime.store.audit("owner_removed_learning_entry", {
        "phrase": payload.phrase, "target": payload.target,
    })
    return {"status": "removed", "phrase": payload.phrase, "candidate_rows_removed": removed_candidates}


@router.post("/learning/reset")
def reset_learning(payload: ResetLearningRequest) -> dict[str, Any]:
    if not payload.confirmed:
        return {"status": "confirmation_required", "message": "This removes learned aliases, candidates, negative examples, semantic examples, pending signals, episodes and macros."}
    if runtime.semantic is not None:
        runtime.semantic.clear_user_examples()
    result = runtime.store.remove_all_user_learning()
    for action in runtime.registry.all():
        if action.name.startswith("macro."):
            runtime.registry.unregister(action.name)
    runtime.store.audit("owner_reset_all_learning", result)
    return {"status": "reset", **result}


@router.get("/learning")
def get_learning_state() -> dict[str, Any]:
    return {
        "aliases": runtime.store.aliases(),
        "candidates": runtime.store.alias_candidates(),
        "negative_examples": runtime.store.negative_examples(),
        "successful_episodes": len(runtime.store.successful_episodes(limit=10000)),
    }


@router.get("/learning/digest")
def learning_digest() -> dict[str, Any]:
    summary = runtime.store.get_setting("learning.last_digest", {})
    proposals = runtime.lexicon.promotion_candidates()
    demoted = int(summary.get("aliases_demoted", 0))
    return {
        "message": f"Learning digest: {len(proposals)} items ready for review; {demoted} entries demoted in the last consolidation.",
        "ready_for_approval": proposals,
        "last_consolidation": summary,
        "owner_action_required": bool(proposals),
    }


@router.post("/learning/candidates/approve")
def approve_learning_candidate(payload: LearningCandidateRequest) -> dict[str, Any]:
    if not payload.confirmed:
        return {
            "status": "confirmation_required",
            "phrase": payload.phrase,
            "action": payload.action_name,
        }
    action = runtime.registry.get(payload.action_name)
    if action is None:
        raise HTTPException(404, "Unknown registered action.")
    try:
        result = runtime.lexicon.approve_candidate(
            payload.phrase, payload.action_name, action.risk,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "status": result.status, "phrase": result.phrase,
        "action": result.target, "confidence": result.confidence,
        "independent_sessions": result.sessions,
    }


@router.post("/learning/candidates/reject")
def reject_learning_candidate(payload: LearningCandidateRequest) -> dict[str, Any]:
    if not payload.confirmed:
        return {"status": "confirmation_required", "phrase": payload.phrase}
    action = runtime.registry.get(payload.action_name)
    if action is None:
        raise HTTPException(404, "Unknown registered action.")
    removed = runtime.lexicon.reject_candidate(payload.phrase, payload.action_name)
    if not removed:
        raise HTTPException(404, "Learning candidate not found.")
    return {"status": "rejected", "phrase": payload.phrase, "action": payload.action_name}


@router.post("/learning/consolidate")
def consolidate_learning() -> dict[str, Any]:
    result = runtime.lexicon.consolidate()
    return {"status": "completed", **result}


@router.get("/perception")
def get_perception() -> dict[str, Any]:
    indexed = runtime.refresh_entities()
    return {
        "snapshot": runtime.perception.snapshot(),
        "index": indexed,
        "entities": runtime.store.entity_rows(),
    }


@router.post("/plans/validate")
def validate_agent_plan(payload: AgentPlan) -> dict[str, Any]:
    result = validate_plan(payload, runtime.registry, runtime.settings.agent_max_plan_steps)
    return result.model_dump()


@router.get("/goals")
def list_goals() -> list[dict[str, Any]]:
    return runtime.store.goals(("pending", "active", "completed", "blocked", "cancelled"))


@router.post("/goals", status_code=201)
async def create_goal(payload: GoalCreateRequest) -> dict[str, Any]:
    plan = payload.plan
    if plan is None:
        preview = await runtime.preview(payload.description)
        if preview.get("status") != "selected" or not preview.get("action"):
            raise HTTPException(
                422,
                detail={
                    "message": "Prixon could not form a grounded goal plan.",
                    "decision": preview,
                },
            )
        action = runtime.registry.get(preview["action"])
        if action is None:
            raise HTTPException(422, "The selected action is not registered.")
        args = dict(preview.get("args") or {})
        plan = AgentPlan(
            goal=payload.description,
            steps=[{
                "tool": action.name,
                "args": args,
                "depends_on": [],
                "expected_outcome": ", ".join(action.postconditions),
                "confidence": float(preview.get("confidence", 0.0)),
            }],
        )
    validation = validate_plan(plan, runtime.registry, runtime.settings.agent_max_plan_steps)
    if not validation.valid:
        raise HTTPException(422, detail={"message": "Invalid goal plan.", "errors": validation.errors})
    if any(
        runtime.registry.get(step.tool).risk == RiskTier.ALWAYS_CONFIRM
        for step in plan.steps
    ) and not payload.confirmed:
        raise HTTPException(
            409,
            detail={"message": "This goal contains an L4 action. Review and resubmit the complete plan with confirmed=true."},
        )
    goal_id = runtime.create_goal(
        payload.description, payload.priority, plan, confirmed=payload.confirmed,
    )
    return {
        "id": goal_id,
        "status": "pending",
        "plan": plan.model_dump(mode="json"),
        "message": "Explicit goal stored. The agent loop will process it while running; L4 actions still require confirmation.",
    }


@router.post("/goals/{goal_id}/status")
def update_goal_status(goal_id: str, payload: GoalStatusRequest) -> dict[str, Any]:
    try:
        updated = runtime.store.set_goal_status(goal_id, payload.status)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not updated:
        raise HTTPException(404, "Goal not found.")
    runtime.store.audit("goal_status_changed", {"goal_id": goal_id, "status": payload.status})
    return {"id": goal_id, "status": payload.status}


@router.post("/runtime/start")
async def start_runtime() -> dict[str, Any]:
    return await agent_loop.start()


@router.post("/runtime/stop")
async def stop_runtime() -> dict[str, Any]:
    return await agent_loop.stop("api_stop_requested")


@router.post("/kill")
async def kill_agent() -> dict[str, Any]:
    runtime.kill_switch.trigger("api_kill_requested")
    if not agent_loop.running:
        return {"status": "halted", "reason": runtime.kill_switch.reason}
    return {"status": "halt_requested", "reason": runtime.kill_switch.reason}


@router.get("/runtime/status")
def runtime_status() -> dict[str, Any]:
    return {
        "running": agent_loop.running,
        "event_queue_size": agent_loop.bus.size,
        "kill_switch_active": runtime.kill_switch.active,
        "kill_switch_reason": runtime.kill_switch.reason,
        "voice_kill": agent_loop.voice_kill.status(),
        "suggestions_pending": len(agent_loop.suggestions()),
    }


@router.get("/voice/status")
def voice_status() -> dict[str, Any]:
    return agent_loop.voice_kill.status()


@router.get("/voice/commands")
def voice_commands(limit: int = Query(10, ge=1, le=50)) -> list[dict[str, Any]]:
    """In-memory outcomes from push-to-talk commands; recognized transcripts are not returned."""
    return agent_loop.voice_results(limit)


@router.get("/suggestions")
def list_suggestions(limit: int = Query(30, ge=1, le=100)) -> list[dict[str, Any]]:
    return agent_loop.suggestions()[-limit:]


@router.post("/proactive/feedback")
def proactive_feedback(payload: ProactiveFeedbackRequest) -> dict[str, Any]:
    runtime.proactive.record_response(payload.trigger, payload.accepted)
    return {"status": "recorded"}


@router.get("/events")
def list_pending_events(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    return runtime.store.pending_events(limit)


@router.get("/audit")
def list_audit(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    return runtime.store.audit_rows(limit)


@router.get("/audit/export")
def export_audit(
    after_id: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=50000),
) -> Response:
    rows = runtime.store.audit_export_rows(after_id=after_id, limit=limit)
    body = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\\n" for row in rows)
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="prixon-audit.jsonl"'},
    )


@router.get("/audit/archives")
def list_audit_archives() -> list[dict[str, Any]]:
    return runtime.store.audit_archives()


@router.get("/audit/archives/{filename}")
def download_audit_archive(filename: str) -> FileResponse:
    try:
        path = runtime.store.audit_archive_path(filename)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/x-ndjson",
        filename=path.name,
    )


@router.get("/world-state")
def get_world_state(limit: int = Query(30, ge=1, le=100)) -> dict[str, Any]:
    return {
        "latest": runtime.store.latest_world_state(),
        "history": runtime.store.world_state_rows(limit),
    }


@router.post("/undo/{undo_id}")
def undo_action(undo_id: str) -> dict[str, Any]:
    return runtime.undo(undo_id)


@router.get("/macros")
def list_macros(approved: bool | None = None) -> list[dict[str, Any]]:
    return runtime.list_macros(approved)


@router.post("/macros/{macro_id}/approve")
def approve_macro(macro_id: int, payload: MacroApprovalRequest) -> dict[str, Any]:
    changed = runtime.store.approve_macro(macro_id, payload.approved)
    if not changed:
        raise HTTPException(404, "Macro proposal not found.")
    runtime.store.audit("macro_approval_changed", {
        "macro_id": macro_id, "approved": payload.approved,
    })
    runtime._register_approved_macros()
    return {"id": macro_id, "approved": payload.approved}


@router.post("/macros/{macro_id}/run")
async def run_macro(macro_id: int, payload: MacroRunRequest) -> dict[str, Any]:
    return await runtime.run_macro(
        macro_id, payload.args, execute=payload.execute, confirmed=payload.confirmed,
    )


@router.post("/governance/check")
def governance_check(payload: dict[str, Any]) -> dict[str, Any]:
    action = runtime.registry.get(str(payload.get("action", "")))
    if action is None:
        return {"allowed": False, "reason": "unknown_action"}
    macro_allowlisted = action.name.startswith("macro.") and (
        runtime._macro_id_for_action(action.name) is not None
        and any(item["id"] == runtime._macro_id_for_action(action.name) for item in runtime.store.macros(approved=True))
    )
    outcome = decide(
        action.risk, confirmed=bool(payload.get("confirmed", False)),
        allowlisted=macro_allowlisted,
    )
    return {
        "allowed": outcome.allowed,
        "requires_confirmation": outcome.requires_confirmation,
        "autonomy_level": outcome.autonomy_level,
        "reason": outcome.reason,
    }


@router.get("/model/metrics")
def model_metrics() -> dict[str, Any]:
    return {
        "configured_model": runtime.ollama.model,
        "endpoint": runtime.ollama.base_url,
        "mode": "local_only",
        "last_call": runtime.ollama.last_metrics,
        "summary": runtime.ollama.metrics_summary(),
        "recent_calls": list(runtime.ollama.metrics_history)[-20:],
    }


@router.get("/routines")
def list_routines(enabled: bool | None = None) -> list[dict[str, Any]]:
    return runtime.store.routines(enabled)


@router.post("/routines", status_code=201)
def create_routine(payload: RoutineCreateRequest) -> dict[str, Any]:
    macro = next(
        (item for item in runtime.store.macros(approved=True) if item["id"] == payload.macro_id),
        None,
    )
    if macro is None:
        raise HTTPException(404, "Only an owner-approved macro can be scheduled.")
    try:
        routine_id = runtime.store.create_routine(
            payload.name, payload.macro_id, payload.time_local, payload.weekdays,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    runtime.store.audit("routine_created", {
        "routine_id": routine_id, "macro_id": payload.macro_id,
        "time_local": payload.time_local, "weekdays": payload.weekdays,
    })
    return {
        "id": routine_id, "status": "scheduled",
        "timezone": "system_local", "time_local": payload.time_local,
        "weekdays": payload.weekdays,
        "execution": "suggestion_only",
    }


@router.post("/routines/{routine_id}/status")
def set_routine_status(routine_id: int, payload: RoutineStatusRequest) -> dict[str, Any]:
    changed = runtime.store.set_routine_enabled(routine_id, payload.enabled)
    if not changed:
        raise HTTPException(404, "Routine not found.")
    runtime.store.audit("routine_status_changed", {
        "routine_id": routine_id, "enabled": payload.enabled,
    })
    return {"id": routine_id, "enabled": payload.enabled}


@router.delete("/routines/{routine_id}")
def delete_routine(routine_id: int) -> dict[str, Any]:
    if not runtime.store.delete_routine(routine_id):
        raise HTTPException(404, "Routine not found.")
    runtime.store.audit("routine_deleted", {"routine_id": routine_id})
    return {"status": "deleted", "id": routine_id}
