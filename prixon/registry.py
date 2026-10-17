from __future__ import annotations

from prixon.schemas import ActionSpec, IntentClass, RiskTier


class ActionRegistry:
    """Allowlisted action contracts; models can select identifiers, never define commands."""

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

    def unregister(self, name: str) -> bool:
        return self._actions.pop(name, None) is not None

    def all(self) -> list[ActionSpec]:
        return list(self._actions.values())

    def by_class(self, intent_class: IntentClass) -> list[ActionSpec]:
        return [action for action in self._actions.values() if action.intent_class == intent_class]

    def shortlist(self, names: list[str], limit: int = 5) -> list[ActionSpec]:
        return [self._actions[name] for name in names if name in self._actions][:limit]


def default_actions() -> list[ActionSpec]:
    return [
        ActionSpec(
            name="system.status", description="Read a compact Windows system status snapshot.",
            examples=("system status", "how is my pc doing", "show system health", "check my computer",
                      "is my computer okay", "give me a pc health summary"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="system",
            hard_negatives=("list running processes", "is spotify running"),
            postconditions=("status_snapshot_returned",),
        ),
        ActionSpec(
            name="process.list", description="List currently running processes.",
            examples=("list running processes", "what apps are running", "show active applications",
                      "display the process list", "what is running on my pc"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="process_collection",
            hard_negatives=("check if spotify is running", "is chrome running"),
            postconditions=("process_list_returned",),
        ),
        ActionSpec(
            name="app.is_running", description="Check whether a specific application process is running.",
            examples=("is spotify running", "check if chrome is running", "is notepad open",
                      "tell me whether discord is active"),
            intent_class=IntentClass.QUERY, verb_type="inspect", target_type="application",
            required_slots=("application",),
            parameter_schema={"application": "entity:application_or_process"},
            hard_negatives=("list running processes", "show all processes"),
            postconditions=("application_running_state_returned",),
        ),
        ActionSpec(
            name="system.memory", description="Read physical memory usage and availability.",
            examples=("show RAM usage", "how much memory is free", "check available RAM",
                      "how much ram am I using", "memory usage"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="memory",
            postconditions=("memory_snapshot_returned",),
        ),
        ActionSpec(
            name="system.cpu", description="Read processor utilization.",
            examples=("check cpu usage", "how busy is my processor", "show cpu load",
                      "processor usage", "cpu percentage"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="processor",
            postconditions=("cpu_snapshot_returned",),
        ),
        ActionSpec(
            name="system.wifi", description="Read Wi-Fi adapter connection status.",
            examples=("is wifi connected", "check wifi connection", "show wireless status",
                      "is my wireless connected", "wifi status"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="wifi",
            postconditions=("wifi_status_returned",),
        ),
        ActionSpec(
            name="system.audio", description="Read the Windows master audio level.",
            examples=("check volume", "what is my volume", "current audio level",
                      "show master volume"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="audio",
            postconditions=("audio_level_returned",),
        ),
        ActionSpec(
            name="system.battery", description="Read battery charge and power state.",
            examples=("check battery", "how much battery is left", "battery percentage",
                      "tell me my remaining charge", "is my laptop plugged in"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="battery",
            postconditions=("battery_snapshot_returned",),
        ),
        ActionSpec(
            name="system.network", description="Read network interface and byte-counter status.",
            examples=("check network status", "show network diagnostics", "how is wifi",
                      "show my network activity", "is the internet interface connected"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="network",
            postconditions=("network_snapshot_returned",),
        ),
        ActionSpec(
            name="app.launch", description="Launch a grounded installed application by its registered identity.",
            examples=("open notepad", "launch calculator", "fire up paint", "start calculator"),
            intent_class=IntentClass.LAUNCH, verb_type="launch", target_type="installed_application",
            required_slots=("application",),
            parameter_schema={"application": "entity:application", "application_target": "path:allowlisted"},
            preconditions=("installed_application_resolves",),
            postconditions=("target_process_started",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("native_api", "shell_uri"),
        ),
        ActionSpec(
            name="window.minimize", description="Minimize the grounded foreground window.",
            examples=("minimize this window", "minimize current window", "minimize it"),
            intent_class=IntentClass.CONTROL, verb_type="minimize", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists",), postconditions=("window_is_minimized",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("win32",),
        ),
        ActionSpec(
            name="window.maximize", description="Maximize the grounded foreground window.",
            examples=("maximize this window", "maximize it", "make this window full size"),
            intent_class=IntentClass.CONTROL, verb_type="maximize", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists",), postconditions=("window_is_maximized",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("win32",),
        ),
        ActionSpec(
            name="window.restore", description="Restore the grounded foreground window.",
            examples=("restore this window", "unminimize this window", "restore it"),
            intent_class=IntentClass.CONTROL, verb_type="restore", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists",), postconditions=("window_is_restored",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("win32",),
        ),
        ActionSpec(
            name="window.close", description="Send a graceful close request to the grounded foreground window.",
            examples=("close this window", "close it", "close the current app"),
            intent_class=IntentClass.CONTROL, verb_type="close", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists", "owner_confirmed"),
            postconditions=("window_closed_or_close_prompt_shown",),
            risk=RiskTier.ALWAYS_CONFIRM, undo_supported=False, automation_tiers=("win32",),
        ),
        ActionSpec(
            name="volume.set", description="Set Windows master volume to a requested level.",
            examples=("set volume to 30 percent", "turn volume down to 20", "volume at 50"),
            intent_class=IntentClass.SYSTEM_SETTING, verb_type="set", target_type="audio_volume",
            required_slots=("level",), parameter_schema={"level": "number:0..100"},
            preconditions=("audio_endpoint_available",),
            postconditions=("volume_equals_requested_level",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("native_api",),
        ),
        ActionSpec(
            name="settings.open", description="Open an allowlisted Windows Settings page.",
            examples=("open display settings", "open sound settings", "open bluetooth settings",
                      "open wifi settings", "open battery settings", "open night light settings"),
            intent_class=IntentClass.SYSTEM_SETTING, verb_type="open", target_type="settings_page",
            required_slots=("setting",), parameter_schema={"setting": "enum:approved_settings_uri"},
            preconditions=("setting_uri_allowlisted",), postconditions=("settings_page_opened",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("uri_scheme",),
        ),
        ActionSpec(
            name="file.quarantine", description="Move an explicitly selected user file into a restorable quarantine folder.",
            examples=("quarantine this file", "move selected file to quarantine"),
            intent_class=IntentClass.FILE_OPERATION, verb_type="move", target_type="file",
            required_slots=("file",), parameter_schema={"file": "path:user_profile_file"},
            preconditions=("file_exists_in_user_profile", "owner_confirmed"),
            postconditions=("file_in_quarantine",),
            risk=RiskTier.ALWAYS_CONFIRM, undo_supported=True, automation_tiers=("native_api",),
        ),
    ]
