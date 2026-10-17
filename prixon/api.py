from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from prixon.agent_loop import AgentLoop
from prixon.governance import decide
from prixon.planner import validate_plan
from prixon.runtime import AgentRuntime
from prixon.schemas import (
    AgentPlan,
    AliasFeedbackRequest,
    DeleteAliasRequest,
    DecisionRequest,
    EntityAliasRequest,
    GoalCreateRequest,
    GoalStatusRequest,
    MacroApprovalRequest,
    MacroRunRequest,
    ProactiveFeedbackRequest,
    RunRequest,
    ResetLearningRequest,
    TeachAliasRequest,
)
from prixon.store import AgentStore

router = APIRouter(prefix="/api/v1/agent", tags=["Prixon Agent"])

# One local agent runtime per API process. The runtime owns SQLite and local Ollama only.
runtime = AgentRuntime()
agent_loop = AgentLoop(runtime)


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
        return {"status": "confirmation_required", "message": "This removes learned aliases, candidates, negative examples, semantic examples and macros."}
    result = runtime.store.remove_all_user_learning()
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
    goal_id = runtime.create_goal(payload.description, payload.priority, plan)
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
        "suggestions_pending": len(agent_loop.suggestions()),
    }


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
    outcome = decide(action.risk, confirmed=bool(payload.get("confirmed", False)))
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
    }
