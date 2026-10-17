from __future__ import annotations

from prixon.schemas import ActionSpec, IntentClass, RiskTier


class ActionRegistry:
    """Allowlisted action contracts; models can select identifiers, never define commands."""

    def __init__(self, actions: list[ActionSpec] | None = None) -> None:
        self._actions: dict[str, ActionSpec] = {}
        for action in actions or default_actions():
            self.register(action)

    def register(self, action: ActionSpec) -> None:
        if action.risk == RiskTier.READ_ONLY and not action.idempotent:
            action = action.model_copy(update={
                "idempotent": True,
                "retry_policy": "once_if_idempotent",
            })
        safe_retries = {"window.minimize", "window.maximize", "window.restore", "volume.set"}
        if action.name in safe_retries and not action.idempotent:
            action = action.model_copy(update={
                "idempotent": True,
                "retry_policy": "once_if_idempotent",
            })
        if action.name in self._actions:
            raise ValueError(f"Duplicate action: {action.name}")
        action_timeouts = {
            "app.launch": 8.0,
            "media.status": 5.0,
            "media.play": 5.0,
            "media.pause": 5.0,
            "media.stop": 5.0,
            "media.skip_next": 5.0,
            "media.skip_previous": 5.0,
            "office.status": 5.0,
            "browser.debug_status": 3.0,
            "clipboard.inspect": 3.0,
            "clipboard.read": 3.0,
            "ui.activate_control": 4.0,
        }
        timeout = action_timeouts.get(action.name)
        if timeout is not None and action.timeout_seconds == 12.0:
            action = action.model_copy(update={"timeout_seconds": timeout})
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
                      "is my computer okay", "give me a pc health summary",
                      "show a quick pc health report", "run a computer health check",
                      "how is this pc performing", "show the current system overview",
                      "check my pc health", "report computer status",
                      "how is my system holding up", "give me a system status"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="system",
            hard_negatives=("list running processes", "is spotify running"),
            postconditions=("status_snapshot_returned",),
        ),
        ActionSpec(
            name="process.list", description="List currently running processes.",
            examples=("list running processes", "what apps are running", "show active applications",
                      "display the process list", "what is running on my pc",
                      "list all active processes", "show processes currently running",
                      "display every running process", "which applications are running",
                      "show me open apps", "give me the process list",
                      "what is currently running on windows", "show background processes"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="process_collection",
            hard_negatives=("check if spotify is running", "is chrome running"),
            postconditions=("process_list_returned",),
        ),
        ActionSpec(
            name="app.is_running", description="Check whether a specific application process is running.",
            examples=("is spotify running", "check if chrome is running", "is notepad open",
                      "tell me whether discord is active", "is spotify open",
                      "is chrome currently running", "check whether notepad is open",
                      "tell me if discord is running", "is calculator active",
                      "is edge running", "verify whether paint is running",
                      "is vscode open"),
            intent_class=IntentClass.QUERY, verb_type="inspect", target_type="application",
            required_slots=("application",),
            parameter_schema={"application": "entity:application_or_process"},
            hard_negatives=("list running processes", "show all processes"),
            postconditions=("application_running_state_returned",),
        ),
        ActionSpec(
            name="system.memory", description="Read physical memory usage and availability.",
            examples=("show RAM usage", "how much memory is free", "check available RAM",
                      "how much ram am I using", "memory usage",
                      "show available memory", "report current memory use",
                      "how much physical memory is left", "check my ram consumption",
                      "give me a memory report"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="memory",
            postconditions=("memory_snapshot_returned",),
        ),
        ActionSpec(
            name="system.cpu", description="Read processor utilization.",
            examples=("check cpu usage", "how busy is my processor", "show cpu load",
                      "processor usage", "cpu percentage",
                      "report current processor load", "how much cpu is being used",
                      "show my processor utilization", "check the cpu on this pc"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="processor",
            postconditions=("cpu_snapshot_returned",),
        ),
        ActionSpec(
            name="system.wifi", description="Read Wi-Fi adapter connection status.",
            examples=("is wifi connected", "check wifi connection", "show wireless status",
                      "is my wireless connected", "wifi status",
                      "is wi-fi available", "check whether wireless is connected",
                      "report my wifi connection", "show the wifi adapter state"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="wifi",
            postconditions=("wifi_status_returned",),
        ),
        ActionSpec(
            name="system.audio", description="Read the Windows master audio level.",
            examples=("check volume", "what is my volume", "current audio level",
                      "show master volume", "what is the current sound level",
                      "read the speaker volume", "how loud is the pc right now",
                      "tell me the current audio volume"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="audio",
            postconditions=("audio_level_returned",),
        ),
        ActionSpec(
            name="system.battery", description="Read battery charge and power state.",
            examples=("check battery", "how much battery is left", "battery percentage",
                      "tell me my remaining charge", "is my laptop plugged in",
                      "what charge is left", "report battery health level",
                      "show remaining battery", "how long can the battery last"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="battery",
            postconditions=("battery_snapshot_returned",),
        ),
        ActionSpec(
            name="system.network", description="Read network interface and byte-counter status.",
            examples=("check network status", "show network diagnostics", "how is wifi",
                      "show my network activity", "is the internet interface connected",
                      "report network interface status", "show sent and received bytes",
                      "check my internet connection", "give me network diagnostics"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="network",
            postconditions=("network_snapshot_returned",),
        ),
        ActionSpec(
            name="app.launch", description="Launch a grounded installed application by its registered identity.",
            examples=("open notepad", "open calculator", "launch calculator", "fire up paint", "start calculator",
                      "open visual studio code", "launch spotify", "start brave browser",
                      "open the installed chrome app", "bring up notepad",
                      "run calculator", "start microsoft edge", "open discord"),
            intent_class=IntentClass.LAUNCH, verb_type="launch", target_type="installed_application",
            required_slots=("application",),
            parameter_schema={"application": "entity:application", "application_target": "path:allowlisted"},
            preconditions=("installed_application_resolves",),
            postconditions=("target_process_started",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("native_api",),
        ),
        ActionSpec(
            name="ui.activate_control",
            description="Invoke one explicitly named, visible button/menu/tab control in the foreground application using UI Automation.",
            examples=(
                "click the save button", "activate the open button",
                "click the settings menu", "select the home tab",
                "press the refresh button", "click the submit button",
                "activate the selected menu item",
            ),
            hard_negatives=(
                "open the application", "launch the program",
                "read the page", "type into the form", "enter my password",
            ),
            intent_class=IntentClass.CONTROL, verb_type="activate", target_type="window",
            required_slots=("hwnd", "control_name"),
            parameter_schema={
                "hwnd": "integer",
                "control_name": "string",
                "automation_id": "optional:string",
                "control_type": "optional:string",
            },
            preconditions=("owner_confirmed", "window_exists", "control_exists"),
            postconditions=("registered_control_invoked",),
            risk=RiskTier.ALWAYS_CONFIRM,
            automation_tiers=("ui_automation",),
        ),
        ActionSpec(
            name="window.minimize", description="Minimize the grounded foreground window.",
            examples=("minimize this window", "minimize current window", "minimize it",
                      "put this window away", "send the current window to the taskbar",
                      "minimize that", "hide the foreground window"),
            intent_class=IntentClass.CONTROL, verb_type="minimize", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists",), postconditions=("window_is_minimized",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("native_api", "ui_automation", "keyboard"),
        ),
        ActionSpec(
            name="window.maximize", description="Maximize the grounded foreground window.",
            examples=("maximize this window", "maximize it", "make this window full size",
                      "expand the current window", "fill the screen with this window",
                      "maximize that", "make this app full screen"),
            intent_class=IntentClass.CONTROL, verb_type="maximize", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists",), postconditions=("window_is_maximized",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("native_api", "ui_automation", "keyboard"),
        ),
        ActionSpec(
            name="window.restore", description="Restore the grounded foreground window.",
            examples=("restore this window", "unminimize this window", "restore it",
                      "bring this window back", "restore that", "unminimize it"),
            intent_class=IntentClass.CONTROL, verb_type="restore", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists",), postconditions=("window_is_restored",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("native_api", "ui_automation", "keyboard"),
        ),
        ActionSpec(
            name="window.close", description="Send a graceful close request to the grounded foreground window.",
            examples=("close this window", "close it", "close the current app",
                      "close the foreground window", "exit this window",
                      "close the current window", "shut this app window"),
            intent_class=IntentClass.CONTROL, verb_type="close", target_type="window",
            required_slots=("window",),
            parameter_schema={"window": "entity:window", "hwnd": "integer:window_handle"},
            preconditions=("window_exists", "owner_confirmed"),
            postconditions=("window_closed_or_close_prompt_shown",),
            risk=RiskTier.ALWAYS_CONFIRM, undo_supported=False, automation_tiers=("native_api", "ui_automation"),
        ),
        ActionSpec(
            name="volume.set", description="Set Windows master volume to a requested level.",
            examples=("set volume to 30 percent", "turn volume down to 20", "volume at 50",
                      "set the master volume to 60", "change volume to 25",
                      "lower volume to 10", "raise volume to 80",
                      "adjust the volume to 40 percent"),
            intent_class=IntentClass.SYSTEM_SETTING, verb_type="set", target_type="audio_volume",
            required_slots=("level",), parameter_schema={"level": "number:0..100"},
            preconditions=("audio_endpoint_available",),
            postconditions=("volume_equals_requested_level",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("native_api",),
        ),
        ActionSpec(
            name="media.status",
            description="Read current Windows media playback state without reading track metadata.",
            examples=(
                "what is playing", "is music playing", "check media playback",
                "show media status", "is spotify playing", "what is the playback state",
            ),
            hard_negatives=("list all processes", "show browser history"),
            intent_class=IntentClass.QUERY, verb_type="inspect", target_type="media_session",
            parameter_schema={"application": "optional:entity:media_session"},
            preconditions=("media_session_available",),
            postconditions=("media_status_returned",),
            risk=RiskTier.READ_ONLY, automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="media.play",
            description="Resume the current or explicitly named Windows media session.",
            examples=(
                "play music", "resume music", "continue playback", "start playback",
                "play spotify", "resume spotify", "continue the media",
            ),
            hard_negatives=("open spotify", "launch spotify"),
            intent_class=IntentClass.CONTROL, verb_type="play", target_type="media_session",
            parameter_schema={"application": "optional:entity:media_session"},
            preconditions=("media_session_available",),
            postconditions=("media_playing",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="media.pause",
            description="Pause the current or explicitly named Windows media session.",
            examples=(
                "pause music", "pause playback", "pause spotify", "pause the song",
                "hold the music", "pause the media",
            ),
            hard_negatives=("close spotify", "stop the spotify process"),
            intent_class=IntentClass.CONTROL, verb_type="pause", target_type="media_session",
            parameter_schema={"application": "optional:entity:media_session"},
            preconditions=("media_session_available",),
            postconditions=("media_paused",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="media.stop",
            description="Stop playback in the current or explicitly named Windows media session.",
            examples=(
                "stop music", "stop playback", "stop spotify playback",
                "stop the current media", "end playback",
            ),
            hard_negatives=("close spotify", "stop the spotify app"),
            intent_class=IntentClass.CONTROL, verb_type="stop", target_type="media_session",
            parameter_schema={"application": "optional:entity:media_session"},
            preconditions=("media_session_available",),
            postconditions=("media_stopped",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="media.skip_next",
            description="Skip to the next item in the current or explicitly named Windows media session.",
            examples=(
                "next track", "skip this song", "play the next track",
                "next song", "skip forward one track", "go to the next song",
            ),
            hard_negatives=("next video frame", "forward the browser page"),
            intent_class=IntentClass.CONTROL, verb_type="skip", target_type="media_session",
            parameter_schema={"application": "optional:entity:media_session"},
            preconditions=("media_session_available",),
            postconditions=("media_command_accepted",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="media.skip_previous",
            description="Skip to the previous item in the current or explicitly named Windows media session.",
            examples=(
                "previous track", "go to the previous song", "restart the song",
                "play the last track", "skip back one track",
            ),
            hard_negatives=("restore previous window", "go back in browser"),
            intent_class=IntentClass.CONTROL, verb_type="skip", target_type="media_session",
            parameter_schema={"application": "optional:entity:media_session"},
            preconditions=("media_session_available",),
            postconditions=("media_command_accepted",),
            risk=RiskTier.REVERSIBLE, undo_supported=True,
            automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="office.status",
            description="Inspect active Word, Excel and PowerPoint session counts and unsaved-state counts without reading document content.",
            examples=(
                "check office documents", "how many word documents are open",
                "check if excel has unsaved work", "show office session status",
                "are there any unsaved office documents", "check word excel and powerpoint",
                "how many spreadsheets are open", "check open office sessions",
            ),
            hard_negatives=(
                "read document content", "open an office document", "save all documents",
                "close every office window",
            ),
            intent_class=IntentClass.QUERY, verb_type="inspect", target_type="office_session",
            postconditions=("office_state_returned",),
            risk=RiskTier.READ_ONLY, automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="browser.debug_status",
            description="Inspect local Chromium debugging runtime/version and target type counts without reading URLs, titles or page contents.",
            examples=(
                "check browser debugging status",
                "check the local chromium debug endpoint",
                "show browser runtime metadata",
                "is brave remote debugging available",
                "count active browser target types",
                "check browser developer protocol status",
            ),
            hard_negatives=(
                "show browser history", "read active page", "list open websites",
                "show page titles", "read cookies",
            ),
            intent_class=IntentClass.QUERY, verb_type="inspect", target_type="browser_runtime",
            preconditions=("browser_debug_enabled",),
            postconditions=("browser_debug_metadata_returned",),
            risk=RiskTier.READ_ONLY, automation_tiers=("app_adapter",),
        ),
        ActionSpec(
            name="settings.open", description="Open an allowlisted Windows Settings page.",
            examples=("open display settings", "open sound settings", "open bluetooth settings",
                      "open wifi settings", "open battery settings", "open night light settings",
                      "go to display settings", "bring up network settings",
                      "open the Windows Update settings page", "open focus assist settings"),
            intent_class=IntentClass.SYSTEM_SETTING, verb_type="open", target_type="settings_page",
            required_slots=("setting",), parameter_schema={"setting": "enum:approved_settings_uri"},
            preconditions=("setting_uri_allowlisted",), postconditions=("settings_page_opened",),
            risk=RiskTier.REVERSIBLE, undo_supported=True, automation_tiers=("uri_scheme",),
        ),
        ActionSpec(
            name="clipboard.inspect",
            description="Inspect clipboard formats and availability without reading copied content.",
            examples=(
                "inspect clipboard", "check clipboard formats", "what formats are on clipboard",
                "is there text on my clipboard", "check if anything is copied",
                "show clipboard metadata",
            ),
            hard_negatives=("read clipboard contents", "show me what i copied"),
            intent_class=IntentClass.QUERY, verb_type="inspect", target_type="clipboard_metadata",
            postconditions=("clipboard_metadata_returned",),
            risk=RiskTier.READ_ONLY, automation_tiers=("native_api",),
        ),
        ActionSpec(
            name="clipboard.read",
            description="Read the current Unicode/text clipboard contents only after explicit confirmation.",
            examples=(
                "read clipboard", "what is in my clipboard", "show clipboard contents",
                "what did i copy", "read what i copied", "get copied text",
                "show me the text i copied", "pasteboard contents",
            ),
            hard_negatives=("inspect clipboard formats", "check clipboard metadata"),
            intent_class=IntentClass.QUERY, verb_type="read", target_type="clipboard_text",
            parameter_schema={"max_chars": "integer:1..4000"},
            preconditions=("owner_explicitly_requested_clipboard_text", "owner_confirmed"),
            postconditions=("clipboard_text_returned_without_persistence",),
            risk=RiskTier.ALWAYS_CONFIRM, sensitive_output=True,
            automation_tiers=("native_api",),
        ),
        ActionSpec(
            name="file.quarantine", description="Move an explicitly selected user file into a restorable quarantine folder.",
            examples=("quarantine this file", "move selected file to quarantine",
                      "quarantine the selected document", "move this file into quarantine",
                      "put the selected file in quarantine", "isolate this file safely"),
            intent_class=IntentClass.FILE_OPERATION, verb_type="move", target_type="file",
            required_slots=("file",), parameter_schema={"file": "path:user_profile_file"},
            preconditions=("file_exists_in_user_profile", "owner_confirmed"),
            postconditions=("file_in_quarantine",),
            risk=RiskTier.ALWAYS_CONFIRM, undo_supported=True, automation_tiers=("native_api",),
        ),
    ]
