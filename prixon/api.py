from __future__ import annotations

from fastapi import APIRouter

from prixon.config import PrixonSettings
from prixon.governance import decide
from prixon.ollama import OllamaClient
from prixon.registry import ActionRegistry
from prixon.router import IntentRouter
from prixon.schemas import DecisionRequest, TeachAliasRequest

router = APIRouter(prefix="/api/v1/agent", tags=["Prixon Agent"])
settings = PrixonSettings()
registry = ActionRegistry()
intent_router = IntentRouter(registry)
ollama = OllamaClient(
    settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout_seconds
)
_user_aliases: dict[str, str] = {}


@router.get("/health")
async def agent_health():
    model_status = await ollama.health()
    return {
        "agent": "Prixon",
        "status": "ready",
        "mode": "local_only",
        "ollama": model_status,
        "registered_actions": len(registry.all()),
        "execution_enabled": False,
        "note": "Foundation mode: decisions are previewed; Windows execution is not enabled yet.",
    }


@router.get("/actions")
def list_actions():
    return [action.model_dump(mode="json") for action in registry.all()]


@router.post("/decide")
def decide_intent(payload: DecisionRequest):
    text = payload.text
    for phrase, action_name in _user_aliases.items():
        if phrase in text.casefold():
            text = f"{text} {action_name.replace('.', ' ')}"
    result = intent_router.route(text)
    return result.model_dump(mode="json")


@router.post("/aliases")
def teach_alias(payload: TeachAliasRequest):
    action = registry.get(payload.action_name)
    if action is None:
        return {"status": "rejected", "reason": "unknown_action"}
    if not payload.confirmed:
        return {"status": "pending_confirmation", "phrase": payload.phrase}
    _user_aliases[payload.phrase.casefold()] = payload.action_name
    return {"status": "learned", "phrase": payload.phrase, "action": payload.action_name}


@router.post("/governance/check")
def governance_check(payload: dict):
    action = registry.get(str(payload.get("action", "")))
    if action is None:
        return {"allowed": False, "reason": "unknown_action"}
    outcome = decide(action.risk, confirmed=bool(payload.get("confirmed", False)))
    return {
        "allowed": outcome.allowed,
        "requires_confirmation": outcome.requires_confirmation,
        "autonomy_level": outcome.autonomy_level,
        "reason": outcome.reason,
    }
