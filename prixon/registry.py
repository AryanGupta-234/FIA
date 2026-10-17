from __future__ import annotations

from prixon.schemas import ActionSpec, IntentClass, RiskTier


class ActionRegistry:
    """Allowlisted actions; the model can select these but cannot create commands."""

    def __init__(self, actions: list[ActionSpec] | None = None) -> None:
        self._actions: dict[str, ActionSpec] = {}
        for action in actions or default_actions():
            self.register(action)

    def register(self, action: ActionSpec) -> None:
        if action.name in self._actions:
            raise ValueError(f"Duplicate action: {action.name}")
        self._actions[action.name] = action

    def get(self, name: str) -> ActionSpec | None:
        return self._actions.get(name)

    def all(self) -> list[ActionSpec]:
        return list(self._actions.values())

    def by_class(self, intent_class: IntentClass) -> list[ActionSpec]:
        return [a for a in self._actions.values() if a.intent_class == intent_class]


def default_actions() -> list[ActionSpec]:
    return [
        ActionSpec(
            name="system.status",
            description="Read a compact Windows system status snapshot.",
            examples=("system status", "how is my pc doing", "show system health"),
            intent_class=IntentClass.QUERY,
            verb_type="read",
            target_type="system",
            postconditions=("status_snapshot_returned",),
        ),
        ActionSpec(
            name="process.list",
            description="List currently running processes.",
            examples=("list running processes", "what apps are running"),
            intent_class=IntentClass.QUERY,
            verb_type="read",
            target_type="process_collection",
            postconditions=("process_list_returned",),
        ),
        ActionSpec(
            name="app.launch",
            description="Launch an installed application by its resolved app identity.",
            examples=("open notepad", "launch calculator", "fire up paint"),
            intent_class=IntentClass.LAUNCH,
            verb_type="launch",
            target_type="installed_application",
            required_slots=("application",),
            risk=RiskTier.REVERSIBLE,
            postconditions=("target_process_started",),
            undo_supported=True,
        ),
        ActionSpec(
            name="window.minimize",
            description="Minimize a grounded foreground or named application window.",
            examples=("minimize this window", "minimize notepad"),
            intent_class=IntentClass.CONTROL,
            verb_type="minimize",
            target_type="window",
            required_slots=("window",),
            risk=RiskTier.REVERSIBLE,
            postconditions=("window_is_minimized",),
            undo_supported=True,
        ),
        ActionSpec(
            name="volume.set",
            description="Set the Windows master volume to a specified level.",
            examples=("set volume to 30 percent", "turn volume down to 20"),
            intent_class=IntentClass.SYSTEM_SETTING,
            verb_type="set",
            target_type="audio_volume",
            required_slots=("level",),
            risk=RiskTier.REVERSIBLE,
            postconditions=("volume_equals_requested_level",),
            undo_supported=True,
        ),
        ActionSpec(
            name="file.quarantine",
            description="Move a selected file into a restorable quarantine directory.",
            examples=("quarantine this file", "move this file to quarantine"),
            intent_class=IntentClass.FILE_OPERATION,
            verb_type="move",
            target_type="file",
            required_slots=("file",),
            risk=RiskTier.ALWAYS_CONFIRM,
            postconditions=("file_in_quarantine",),
            undo_supported=True,
        ),
    ]
