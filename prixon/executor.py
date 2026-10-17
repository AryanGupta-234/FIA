from __future__ import annotations

import os
import shutil
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from prixon.app_adapters import WindowsMediaSessionAdapter, WindowsOfficeAdapter
from prixon.governance import decide
from prixon.perception import WindowsPerception
from prixon.registry import ActionRegistry
from prixon.schemas import AgentPlan, RiskTier
from prixon.store import AgentStore


@dataclass
class ExecutionBudget:
    max_steps: int = 8
    max_replans: int = 2
    wall_clock_seconds: float = 60.0
    max_model_tokens: int = 1024
    step_timeout_seconds: float = 12.0
    max_actions_per_minute: int = 20


@dataclass
class ActionResult:
    success: bool
    action: str
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    undo_id: str | None = None
    verified: bool = False


class WindowsActionAdapters:
    """OS adapters. Each operation is a fixed implementation, never a model-built command."""

    SETTINGS_URIS = {
        "display": "ms-settings:display",
        "sound": "ms-settings:sound",
        "network": "ms-settings:network",
        "wifi": "ms-settings:network-wifi",
        "bluetooth": "ms-settings:bluetooth",
        "battery": "ms-settings:batterysaver",
        "night light": "ms-settings:nightlight",
        "focus": "ms-settings:quiethours",
        "windows update": "ms-settings:windowsupdate",
    }

    def __init__(self, perception: WindowsPerception) -> None:
        self.perception = perception
        self.media = WindowsMediaSessionAdapter()
        self.office = WindowsOfficeAdapter()
        self._uia_cache: dict[int, tuple[float, list[dict[str, str]]]] = {}
        self._uia_cache_lock = threading.Lock()
        self._uia_cache_ttl_seconds = 3.0

    def invalidate_window_cache(self, hwnd: int | None = None) -> None:
        with self._uia_cache_lock:
            if hwnd is None:
                self._uia_cache.clear()
            else:
                self._uia_cache.pop(int(hwnd), None)

    def capture_before(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        if action.startswith("window."):
            hwnd = self._window_handle(args)
            if hwnd and os.name == "nt":
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                return {"hwnd": hwnd, "iconic": bool(user32.IsIconic(hwnd)),
                        "zoomed": bool(user32.IsZoomed(hwnd)),
                        "rect": [rect.left, rect.top, rect.right, rect.bottom]}
        if action == "settings.open":
            foreground = self.perception._foreground_window()
            return {"previous_hwnd": foreground.get("handle") if foreground else None}
        if action == "volume.set":
            return {"volume": self._get_volume()}
        if action.startswith("media.") and action != "media.status":
            return self.media.snapshot(args)
        if action == "file.quarantine":
            return {"original_path": str(self._validated_user_file(args.get("file")))}
        return {}

    @staticmethod
    def _window_handle(args: dict[str, Any]) -> int | None:
        value = args.get("hwnd")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_windows() -> None:
        if os.name != "nt":
            raise OSError("This Prixon action is available only on Windows 11.")

    def check_preconditions(
        self,
        action_name: str,
        preconditions: tuple[str, ...],
        args: dict[str, Any],
        *,
        confirmed: bool,
        utterance: str,
    ) -> str | None:
        """Evaluate the allowlisted predicate vocabulary on fresh machine state."""
        for precondition in preconditions:
            if precondition == "owner_confirmed":
                if not confirmed:
                    return "owner_confirmation_required"
            elif precondition == "owner_explicitly_requested_clipboard_text":
                explicit_terms = (
                    "clipboard", "pasteboard", "what did i copy", "what i copied",
                )
                if action_name != "clipboard.read" or not any(
                    term in utterance.casefold() for term in explicit_terms
                ):
                    return "clipboard_text_requires_an_explicit_owner_request"
            elif precondition == "installed_application_resolves":
                try:
                    target = str(args.get("application_target") or "")
                    self._validate_launch_target(target)
                except (OSError, ValueError) as exc:
                    return f"installed_application_not_available:{type(exc).__name__}"
            elif precondition == "window_exists":
                if os.name != "nt":
                    return "windows_only"
                hwnd = self._window_handle(args)
                if not hwnd:
                    return "grounded_window_handle_missing"
                import ctypes
                user32 = ctypes.windll.user32
                if not user32.IsWindow(hwnd):
                    return "target_window_no_longer_exists"
                length = user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(min(length + 1, 256))
                user32.GetWindowTextW(hwnd, buffer, len(buffer))
                if WindowsPerception._is_sensitive_title(buffer.value):
                    return "sensitive_window_target_blocked"
            elif precondition == "audio_endpoint_available":
                try:
                    self._audio_endpoint()
                except Exception as exc:
                    return f"audio_endpoint_unavailable:{type(exc).__name__}"
            elif precondition == "media_session_available":
                try:
                    self.media.snapshot(args)
                except Exception as exc:
                    return f"media_session_unavailable:{type(exc).__name__}"
            elif precondition == "office_automation_available":
                if os.name != "nt":
                    return "windows_only"
                try:
                    import pythoncom  # noqa: F401
                    import win32com.client  # noqa: F401
                except ImportError:
                    return "office_automation_dependency_missing"
            elif precondition == "setting_uri_allowlisted":
                setting = str(args.get("setting") or "").casefold().strip()
                if setting not in self.SETTINGS_URIS:
                    return "setting_uri_not_allowlisted"
            elif precondition == "file_exists_in_user_profile":
                try:
                    self._validated_user_file(args.get("file"))
                except (OSError, ValueError) as exc:
                    return f"user_file_not_available:{type(exc).__name__}"
            else:
                return f"unsupported_precondition:{precondition}"
        return None

    def execute_tier(
        self, action: str, args: dict[str, Any], tier: str,
    ) -> dict[str, Any]:
        if tier == "app_adapter":
            if action.startswith("media."):
                return self.media.execute(action, args)
            if action.startswith("office."):
                return self.office.execute(action, args)
            raise ValueError(f"No tier-2 adapter is registered for {action}.")
        if tier in {"native_api", "win32", "uri_scheme", "shell_uri"}:
            return self.execute(action, args)
        if tier == "ui_automation":
            return self._execute_ui_automation(action, args)
        if tier == "keyboard":
            return self._execute_keyboard(action, args)
        raise ValueError(f"Unsupported automation tier: {tier}")

    def _execute_ui_automation(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        if action not in {
            "window.minimize", "window.maximize", "window.restore", "window.close",
        }:
            raise ValueError(f"UI Automation fallback is not registered for {action}.")
        try:
            from pywinauto import Application
        except ImportError as exc:
            raise RuntimeError("UI Automation fallback requires the optional pywinauto extra.") from exc
        hwnd = self._window_handle(args)
        if not hwnd:
            raise ValueError("A grounded window handle is required.")
        app = Application(backend="uia").connect(handle=hwnd, timeout=2)
        window = app.window(handle=hwnd)
        if action == "window.minimize":
            window.minimize()
        elif action == "window.maximize":
            window.maximize()
        elif action == "window.restore":
            window.restore()
        else:
            window.close()
        return {
            "hwnd": hwnd,
            "iconic": bool(window.is_minimized()) if action != "window.close" else False,
            "zoomed": bool(window.is_maximized()) if action != "window.close" else False,
            "close_requested": action == "window.close",
            "automation_tier": "ui_automation",
        }

    def describe_window_controls(
        self, hwnd: int, limit: int = 12,
    ) -> list[dict[str, str]]:
        """Return a cached tiny UIA summary, never raw UI trees or form/text values."""
        if os.name != "nt" or not hwnd:
            return []
        cache_key = int(hwnd)
        now = time.monotonic()
        with self._uia_cache_lock:
            cached = self._uia_cache.get(cache_key)
            if cached and now - cached[0] <= self._uia_cache_ttl_seconds:
                return [dict(item) for item in cached[1][:max(1, min(limit, 12))]]
        windows = self.perception.open_windows(limit=100)
        target = next((item for item in windows if item.get("handle") == int(hwnd)), None)
        if target is None or target.get("sensitive"):
            return []
        try:
            from pywinauto import Application
            app = Application(backend="uia").connect(handle=int(hwnd), timeout=1)
            window = app.window(handle=int(hwnd))
            controls = window.descendants()
        except Exception:
            return []

        allowed_roles = {
            "Button", "MenuItem", "TabItem", "CheckBox", "RadioButton", "SplitButton",
        }
        blocked_terms = (
            "password", "credential", "sign in", "log in", "login", "pin",
            "security", "authenticator", "account number", "credit card",
        )
        result: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for control in controls[:120]:
            try:
                if not control.is_visible():
                    continue
                info = control.element_info
                role = str(info.control_type or "")
                if role not in allowed_roles:
                    continue
                name = str(info.name or "").strip()
                if (
                    not name or len(name) > 90
                    or any(term in name.casefold() for term in blocked_terms)
                    or self.perception._is_sensitive_title(name)
                ):
                    continue
                automation_id = str(info.automation_id or "")[:64]
                item = (role, name, automation_id)
                if item in seen:
                    continue
                seen.add(item)
                result.append({
                    "role": role,
                    "name": name,
                    "automation_id": automation_id,
                })
                if len(result) >= max(1, min(int(limit), 12)):
                    break
            except Exception:
                continue
        with self._uia_cache_lock:
            self._uia_cache[cache_key] = (time.monotonic(), [dict(item) for item in result])
        # Keep the cache bounded even when many short-lived windows are created.
        if len(self._uia_cache) > 100:
            oldest = sorted(self._uia_cache, key=lambda key: self._uia_cache[key][0])[:25]
            with self._uia_cache_lock:
                for key in oldest:
                    self._uia_cache.pop(key, None)
        return result

    def _execute_keyboard(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        if action not in {"window.minimize", "window.maximize", "window.restore"}:
            raise ValueError(f"Keyboard fallback is not registered for {action}.")
        hwnd = self._window_handle(args)
        if not hwnd:
            raise ValueError("A grounded window handle is required.")
        import ctypes
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            raise ValueError("The grounded target window no longer exists.")
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        if int(user32.GetForegroundWindow()) != hwnd:
            raise RuntimeError("Target window could not be focused; keyboard input was not sent.")

        keybd_event = user32.keybd_event
        keybd_event(0x12, 0, 0, 0)  # ALT down
        keybd_event(0x20, 0, 0, 0)  # SPACE down
        keybd_event(0x20, 0, 0x0002, 0)  # SPACE up
        keybd_event(0x12, 0, 0x0002, 0)  # ALT up
        command = {
            "window.minimize": ord("N"),
            "window.maximize": ord("X"),
            "window.restore": ord("R"),
        }[action]
        keybd_event(command, 0, 0, 0)
        keybd_event(command, 0, 0x0002, 0)
        time.sleep(0.1)
        return {
            "hwnd": hwnd,
            "iconic": bool(user32.IsIconic(hwnd)),
            "zoomed": bool(user32.IsZoomed(hwnd)),
            "automation_tier": "keyboard",
        }

    def execute(self, action: str, args: dict[str, Any]) -> dict[str, Any]:
        if action == "system.status":
            return self.perception.snapshot()
        if action == "process.list":
            return {"processes": self.perception.processes(limit=200)}
        if action == "system.battery":
            return {"battery": self.perception.snapshot()["battery"]}
        if action == "system.memory":
            memory = psutil.virtual_memory()
            return {
                "total_bytes": int(memory.total),
                "available_bytes": int(memory.available),
                "used_bytes": int(memory.used),
                "percent": float(memory.percent),
            }
        if action == "system.cpu":
            return {"cpu_percent": psutil.cpu_percent(interval=0.1), "logical_cores": psutil.cpu_count()}
        if action == "system.wifi":
            adapters = []
            for name, stats in psutil.net_if_stats().items():
                if any(token in name.casefold() for token in ("wi-fi", "wifi", "wireless", "802.11")):
                    adapters.append({
                        "name": name, "is_up": bool(stats.isup),
                        "speed_mbps": int(stats.speed) if stats.speed else None,
                    })
            return {"adapters": adapters, "connected": any(item["is_up"] for item in adapters)}
        if action == "system.audio":
            return {"volume": self._get_volume()}
        if action == "app.is_running":
            mention = str(args.get("application") or "").casefold().strip()
            if not mention:
                raise ValueError("Application name is required.")
            matches = []
            for process in psutil.process_iter(["pid", "name"]):
                try:
                    name = str(process.info.get("name") or "").casefold()
                    if mention in name or name.removesuffix(".exe") == mention.removesuffix(".exe"):
                        matches.append({"pid": int(process.info["pid"]), "name": name})
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            return {"application": mention, "running": bool(matches), "match_count": len(matches)}
        if action == "system.network":
            counters = psutil.net_io_counters()
            return {
                "interfaces": list(psutil.net_if_addrs().keys()),
                "bytes_sent": int(counters.bytes_sent),
                "bytes_received": int(counters.bytes_recv),
                "connections": self._connection_count(),
            }
        if action == "app.launch":
            self._require_windows()
            target = str(args.get("application_target", ""))
            self._validate_launch_target(target)
            before_pids = set(psutil.pids())
            os.startfile(target)  # type: ignore[attr-defined]
            selected_pid = None
            selected_window = None
            app_name = str(args.get("application") or "").casefold()
            process_hints = {
                "paint": ("mspaint.exe", "paintapp.exe"),
                "calculator": ("calculatorapp.exe", "calc.exe"),
                "microsoft edge": ("msedge.exe",),
                "edge": ("msedge.exe",),
                "google chrome": ("chrome.exe",),
                "chrome": ("chrome.exe",),
                "brave": ("brave.exe",),
                "visual studio code": ("code.exe",),
                "vs code": ("code.exe",),
                "spotify": ("spotify.exe",),
                "discord": ("discord.exe",),
            }
            hints = process_hints.get(app_name, (app_name.split()[0] + ".exe",))
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                visible_windows = self.perception.open_windows(limit=100)
                matches = [
                    item for item in visible_windows
                    if not item.get("sensitive")
                    and item.get("pid")
                    and any(
                        hint in str(item.get("process") or "").casefold()
                        for hint in hints
                    )
                ]
                foreground_window = next(
                    (item for item in matches if item.get("foreground")),
                    None,
                )
                selected_window = foreground_window or (matches[0] if matches else None)
                if selected_window:
                    selected_pid = int(selected_window["pid"])
                    break

                # A process may be ready before its top-level window is created.
                candidates = sorted(set(psutil.pids()) - before_pids)
                for pid in candidates:
                    try:
                        process_name = psutil.Process(pid).name().casefold()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                    if any(hint in process_name for hint in hints):
                        selected_pid = int(pid)
                        break
                if selected_pid is not None and not psutil.pid_exists(selected_pid):
                    selected_pid = None
                time.sleep(0.1)

            return {
                "launched": target,
                "application": args.get("application"),
                "pid": selected_pid,
                "hwnd": selected_window.get("handle") if selected_window else None,
                "window": selected_window.get("title") if selected_window else None,
                "window_ready": selected_window is not None,
            }
        if action in {"window.minimize", "window.maximize", "window.restore"}:
            self._require_windows()
            hwnd = self._window_handle(args)
            if not hwnd:
                raise ValueError("A grounded window handle is required.")
            import ctypes
            if not ctypes.windll.user32.IsWindow(hwnd):
                raise ValueError("The target window no longer exists.")
            command = {"window.minimize": 6, "window.maximize": 3, "window.restore": 9}[action]
            ctypes.windll.user32.ShowWindow(hwnd, command)
            return {
                "hwnd": hwnd, "iconic": bool(ctypes.windll.user32.IsIconic(hwnd)),
                "zoomed": bool(ctypes.windll.user32.IsZoomed(hwnd)),
            }
        if action == "window.close":
            self._require_windows()
            hwnd = self._window_handle(args)
            if not hwnd:
                raise ValueError("A grounded window handle is required.")
            import ctypes
            if not ctypes.windll.user32.IsWindow(hwnd):
                raise ValueError("The target window no longer exists.")
            ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
            return {"hwnd": hwnd, "close_requested": True}
        if action == "volume.set":
            level = float(args.get("level", -1))
            if not 0 <= level <= 100:
                raise ValueError("Volume must be between 0 and 100.")
            self._set_volume(level)
            return {"volume": self._get_volume()}
        if action == "settings.open":
            self._require_windows()
            setting = str(args.get("setting", "")).casefold().strip()
            uri = self.SETTINGS_URIS.get(setting)
            if not uri:
                raise ValueError("Setting is not in the approved Settings URI allowlist.")
            os.startfile(uri)  # type: ignore[attr-defined]
            hwnd = None
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                foreground = self.perception._foreground_window()
                if foreground and not foreground.get("sensitive") and foreground.get("handle"):
                    try:
                        process_name = psutil.Process(int(foreground["pid"])).name().casefold()
                        title = str(foreground.get("title") or "").casefold()
                        if process_name == "systemsettings.exe" or "settings" in title:
                            hwnd = int(foreground["handle"])
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                time.sleep(0.1)
            return {"opened_setting": setting, "uri": uri, "hwnd": hwnd}
        if action == "clipboard.inspect":
            return self._clipboard_metadata()
        if action == "clipboard.read":
            return self._clipboard_read(args)
        if action == "file.quarantine":
            self._require_windows()
            source = self._validated_user_file(args.get("file"))
            quarantine = Path(os.environ["LOCALAPPDATA"]) / "Prixon" / "Quarantine"
            quarantine.mkdir(parents=True, exist_ok=True)
            destination = quarantine / f"{uuid.uuid4().hex}_{source.name}"
            shutil.move(str(source), str(destination))
            return {"original_path": str(source), "quarantined_path": str(destination)}
        raise ValueError(f"No executor adapter registered for {action!r}.")

    @staticmethod
    def _open_clipboard():
        try:
            import win32clipboard
        except ImportError as exc:
            raise RuntimeError("Clipboard actions require the optional pywin32 Windows dependency.") from exc
        last_error = None
        for _ in range(5):
            try:
                win32clipboard.OpenClipboard(None)
                return win32clipboard
            except Exception as exc:
                last_error = exc
                time.sleep(0.05)
        raise RuntimeError(f"Windows clipboard is busy: {type(last_error).__name__}")

    def _clipboard_metadata(self) -> dict[str, Any]:
        self._require_windows()
        clipboard = self._open_clipboard()
        try:
            formats: list[dict[str, Any]] = []
            current = 0
            while True:
                current = clipboard.EnumClipboardFormats(current)
                if not current:
                    break
                standard_names = {
                    1: "CF_TEXT",
                    2: "CF_BITMAP",
                    8: "CF_DIB",
                    13: "CF_UNICODETEXT",
                    15: "CF_HDROP",
                    17: "CF_DIBV5",
                }
                try:
                    name = clipboard.GetClipboardFormatName(current)
                except Exception:
                    name = standard_names.get(current, f"FORMAT_{current}")
                formats.append({"id": int(current), "name": str(name)[:100]})
            names = " ".join(item["name"].casefold() for item in formats)
            ids = {item["id"] for item in formats}
            return {
                "formats": formats,
                "format_count": len(formats),
                "text_available": bool({1, 13} & ids),
                "html_available": "html format" in names or "text/html" in names,
                "image_available": bool({2, 8, 17} & ids),
                "file_list_available": 15 in ids,
                "content_read": False,
            }
        finally:
            clipboard.CloseClipboard()

    def _clipboard_read(self, args: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        max_chars = int(args.get("max_chars", 2000))
        if not 1 <= max_chars <= 4000:
            raise ValueError("Clipboard text limit must be between 1 and 4000 characters.")
        clipboard = self._open_clipboard()
        try:
            if clipboard.IsClipboardFormatAvailable(clipboard.CF_UNICODETEXT):
                raw = clipboard.GetClipboardData(clipboard.CF_UNICODETEXT)
                text = raw if isinstance(raw, str) else bytes(raw).decode("utf-16-le", errors="replace")
            elif clipboard.IsClipboardFormatAvailable(clipboard.CF_TEXT):
                raw = clipboard.GetClipboardData(clipboard.CF_TEXT)
                text = raw.decode("mbcs", errors="replace") if isinstance(raw, bytes) else str(raw)
            else:
                raise ValueError("The clipboard does not currently contain plain text.")
        finally:
            clipboard.CloseClipboard()
        returned = text[:max_chars]
        return {
            "text": returned,
            "text_available": True,
            "char_count": len(text),
            "returned_chars": len(returned),
            "truncated": len(text) > len(returned),
            "content_read_explicitly": True,
        }

    @staticmethod
    def _connection_count() -> int | None:
        try:
            return len(psutil.net_connections(kind="inet"))
        except (psutil.AccessDenied, OSError):
            return None

    @staticmethod
    def _validate_launch_target(target: str) -> None:
        path = Path(target).resolve()
        allowed_roots = [
            Path(os.environ.get("APPDATA", "C:/__missing__")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "C:/__missing__")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("WINDIR", "C:/Windows")) / "System32",
        ]
        if path.suffix.casefold() not in {".lnk", ".exe", ".bat", ".cmd"}:
            raise ValueError("Only installed application shortcuts or executables can be launched.")
        if not any(path == root.resolve() or root.resolve() in path.parents for root in allowed_roots):
            raise ValueError("Application target is outside the approved Start Menu/System32 roots.")
        if not path.exists():
            raise FileNotFoundError("The installed application target no longer exists.")

    @staticmethod
    def _validated_user_file(value: Any) -> Path:
        if not value:
            raise ValueError("A file path must be supplied explicitly.")
        raw_path = Path(str(value)).expanduser()
        if raw_path.is_symlink():
            raise ValueError("Symbolic links cannot be moved to quarantine.")
        path = raw_path.resolve(strict=True)
        home = Path.home().resolve()
        if not path.is_file() or (path != home and home not in path.parents):
            raise ValueError("Only an existing regular file inside the user profile can be quarantined.")
        return path

    @staticmethod
    def _audio_endpoint():
        try:
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError as exc:
            raise RuntimeError("Volume control requires the optional Windows audio dependency pycaw.") from exc
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)

    def _get_volume(self) -> float:
        self._require_windows()
        endpoint = self._audio_endpoint()
        return round(float(endpoint.GetMasterVolumeLevelScalar()) * 100, 1)

    def _set_volume(self, level: float) -> None:
        self._require_windows()
        self._audio_endpoint().SetMasterVolumeLevelScalar(level / 100.0, None)

    def undo(self, action: str, args: dict[str, Any], before: dict[str, Any], output: dict[str, Any]) -> bool:
        self._require_windows()
        if action.startswith("window.") and action != "window.close":
            hwnd = int(before.get("hwnd") or output.get("hwnd") or 0)
            if not hwnd:
                return False
            import ctypes
            user32 = ctypes.windll.user32
            if before.get("zoomed"):
                user32.ShowWindow(hwnd, 3)
            elif before.get("iconic"):
                user32.ShowWindow(hwnd, 6)
            else:
                user32.ShowWindow(hwnd, 9)
            if before.get("rect") and not before.get("zoomed") and not before.get("iconic"):
                left, top, right, bottom = before["rect"]
                user32.SetWindowPos(
                    hwnd, 0, left, top, right - left, bottom - top,
                    0x0004 | 0x0010,
                )
            return True
        if action.startswith("media."):
            return self.media.undo(action, args, before, output)
        if action == "settings.open":
            hwnd = int(output.get("hwnd") or 0)
            previous = int(before.get("previous_hwnd") or 0)
            if hwnd and hwnd != previous:
                import ctypes
                return bool(ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0))
            return False
        if action == "volume.set" and before.get("volume") is not None:
            self._set_volume(float(before["volume"]))
            return True
        if action == "app.launch":
            pid = output.get("pid")
            if pid:
                psutil.Process(int(pid)).terminate()
                return True
            return False
        if action == "file.quarantine":
            source = Path(str(output.get("quarantined_path", "")))
            destination = Path(str(before.get("original_path", output.get("original_path", ""))))
            if source.exists() and destination.parent.exists() and not destination.exists():
                shutil.move(str(source), str(destination))
                return True
            return False
        return False


class ActionExecutor:
    def __init__(
        self, registry: ActionRegistry, store: AgentStore,
        perception: WindowsPerception | None = None,
        kill_switch=None, adapters: WindowsActionAdapters | None = None,
        budget: ExecutionBudget | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.perception = perception or WindowsPerception()
        self.adapters = adapters or WindowsActionAdapters(self.perception)
        self.kill_switch = kill_switch
        self.budget = budget or ExecutionBudget()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="PrixonAction")
        self._seen_steps: dict[str, int] = {}
        self._action_times: deque[float] = deque()
        self._rate_lock = threading.Lock()

    def execute_action(
        self, action_name: str, args: dict[str, Any], *,
        confirmed: bool = False, confidence: float = 1.0,
        utterance: str = "", session_id: str = "local-session",
    ) -> ActionResult:
        action = self.registry.get(action_name)
        if action is None:
            return ActionResult(False, action_name, error="unknown_action")
        if self.kill_switch and self.kill_switch.active:
            return ActionResult(False, action_name, error="kill_switch_active")
        if any(key in args for key in ("command", "shell", "script", "powershell")):
            return ActionResult(False, action_name, error="arbitrary_command_arguments_rejected")
        for slot in action.required_slots:
            if slot not in args or args[slot] in (None, ""):
                return ActionResult(False, action_name, error=f"required_slot_missing:{slot}")
        decision = decide(action.risk, confirmed=confirmed)
        if not decision.allowed:
            return ActionResult(
                False, action_name, error=decision.reason,
                output={"requires_confirmation": decision.requires_confirmation},
            )
        from prixon.confidence import meets_risk_threshold
        if action.risk != RiskTier.ALWAYS_CONFIRM and not meets_risk_threshold(
            confidence, action.risk.value,
        ):
            return ActionResult(False, action_name, error="confidence_below_risk_threshold")
        precondition_error = self.adapters.check_preconditions(
            action_name, action.preconditions, args,
            confirmed=confirmed, utterance=utterance,
        )
        if precondition_error:
            self.store.audit("action_precondition_failed", {
                "action": action_name, "precondition_error": precondition_error,
            })
            return ActionResult(False, action_name, error=f"precondition_failed:{precondition_error}")
        if action.risk != RiskTier.READ_ONLY and not action.undo_supported and action.risk != RiskTier.ALWAYS_CONFIRM:
            return ActionResult(False, action_name, error="state_change_without_undo_recipe_blocked")

        # Reserve one request slot atomically; all fallback tiers for this action share it.
        with self._rate_lock:
            now = time.monotonic()
            while self._action_times and now - self._action_times[0] >= 60:
                self._action_times.popleft()
            if len(self._action_times) >= self.budget.max_actions_per_minute:
                return ActionResult(False, action_name, error="action_rate_limit_exceeded")
            self._action_times.append(now)

        try:
            before = self.adapters.capture_before(action_name, args)
        except Exception as exc:
            return ActionResult(False, action_name, error=f"precondition_failed:{type(exc).__name__}:{exc}")
        undo_id = None
        if action.undo_supported:
            undo_id = self.store.record_undo(
                action_name, args, before, utterance=utterance, session_id=session_id,
            )
        failures: list[str] = []
        output: dict[str, Any] = {}
        verified = False
        selected_tier: str | None = None
        for tier in action.automation_tiers or ("native_api",):
            if self.kill_switch and self.kill_switch.active:
                failures.append("kill_switch_active")
                break
            future = self._executor.submit(
                self.adapters.execute_tier, action_name, args, tier,
            )
            try:
                candidate = future.result(timeout=self.budget.step_timeout_seconds)
            except TimeoutError:
                failures.append(f"{tier}:timeout")
                future.cancel()
                self.store.audit("automation_tier_timeout", {
                    "action": action_name, "tier": tier, "args": args,
                })
                # The timed-out worker may still be executing; never start a second
                # implementation of the same state-changing operation concurrently.
                break
            except Exception as exc:
                failures.append(f"{tier}:{type(exc).__name__}:{exc}")
                self.store.audit("automation_tier_failed", {
                    "action": action_name, "tier": tier, "error": str(exc),
                })
                continue

            candidate = dict(candidate)
            candidate["automation_tier"] = tier
            if self.verify(action_name, args, candidate):
                output, selected_tier, verified = candidate, tier, True
                break
            failures.append(f"{tier}:postcondition_failed")
            output, selected_tier = candidate, tier
            self.store.audit("automation_tier_verification_failed", {
                "action": action_name, "tier": tier,
                "output": self.audit_output(action_name, candidate),
            })

        if undo_id:
            self.store.update_undo_output(undo_id, output)
        if not verified:
            self.store.audit("verification_failed", {
                "action": action_name,
                "output": self.audit_output(action_name, output),
                "tier_failures": failures,
            })
            if undo_id:
                try:
                    rolled_back = self.adapters.undo(action_name, args, before, output)
                except Exception:
                    rolled_back = False
                self.store.finish_undo(undo_id, "undone" if rolled_back else "failed")
            reason = "automation_tiers_exhausted:" + "|".join(failures)
            return ActionResult(False, action_name, output, reason, undo_id, False)
        self.store.audit("action_completed", {
            "action": action_name, "args": args,
            "output": self.audit_output(action_name, output),
            "undo_id": undo_id, "automation_tier": selected_tier,
            "tier_failures": failures,
        })
        return ActionResult(True, action_name, output, undo_id=undo_id, verified=True)

    def audit_output(self, action_name: str, output: dict[str, Any]) -> dict[str, Any]:
        action = self.registry.get(action_name)
        if action is None or not action.sensitive_output:
            return dict(output)
        safe = {
            key: value for key, value in output.items()
            if key not in {"text", "content", "clipboard_text"}
        }
        sensitive_text = output.get("text", output.get("content", output.get("clipboard_text", "")))
        safe.update({
            "sensitive_output_redacted": True,
            "sensitive_character_count": len(sensitive_text) if isinstance(sensitive_text, str) else None,
        })
        return safe

    def verify(self, action_name: str, args: dict[str, Any], output: dict[str, Any]) -> bool:
        if action_name in {
            "system.status", "process.list", "system.battery", "system.network",
            "system.memory", "system.cpu", "system.wifi", "system.audio",
        }:
            return bool(output)
        if action_name == "clipboard.inspect":
            return "formats" in output and "content_read" in output
        if action_name == "clipboard.read":
            return isinstance(output.get("text"), str) and output.get("text_available") is True
        if action_name == "media.status":
            return bool(output.get("session_available")) and "playback_status" in output
        if action_name == "office.status":
            return (
                output.get("automation_available") is True
                and "open_document_count" in output
                and "unsaved_document_count" in output
            )
        if action_name == "media.play":
            return bool(output.get("accepted")) and output.get("playback_status") == "playing"
        if action_name == "media.pause":
            return bool(output.get("accepted")) and output.get("playback_status") == "paused"
        if action_name == "media.stop":
            return bool(output.get("accepted")) and output.get("playback_status") == "stopped"
        if action_name in {"media.skip_next", "media.skip_previous"}:
            return bool(output.get("accepted"))
        if action_name == "app.is_running":
            return "running" in output
        if action_name == "app.launch":
            pid = output.get("pid")
            return bool(
                output.get("launched")
                and Path(output["launched"]).exists()
                and pid is not None
                and psutil.pid_exists(int(pid))
            )
        if action_name == "window.minimize":
            return bool(output.get("iconic"))
        if action_name == "window.maximize":
            return bool(output.get("zoomed"))
        if action_name == "window.restore":
            return not bool(output.get("iconic"))
        if action_name == "window.close":
            return bool(output.get("close_requested"))
        if action_name == "volume.set":
            return abs(float(output.get("volume", -100)) - float(args["level"])) <= 2
        if action_name == "settings.open":
            return bool(output.get("opened_setting")) and output.get("hwnd") is not None
        if action_name == "file.quarantine":
            return Path(output.get("quarantined_path", "")).is_file()
        return False

    def execute_plan(
        self, plan: AgentPlan, *, confirmed: bool = False,
        session_id: str = "local-session",
        deadline_monotonic: float | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        deadline = deadline_monotonic or (started + self.budget.wall_clock_seconds)
        self._seen_steps.clear()
        from prixon.planner import validate_plan
        validation = validate_plan(plan, self.registry, self.budget.max_steps)
        if not validation.valid:
            return {
                "status": "rejected", "reason": "plan_validation_failed",
                "errors": validation.errors, "steps": [],
            }
        if any(
            self.registry.get(step.tool).risk == RiskTier.ALWAYS_CONFIRM
            for step in plan.steps
        ) and not confirmed:
            return {
                "status": "confirmation_required",
                "reason": "whole_plan_contains_l4_action",
                "steps": [],
            }
        results: list[dict[str, Any]] = []
        for index, step in enumerate(plan.steps):
            if self.kill_switch and self.kill_switch.active:
                return {"status": "aborted", "reason": "kill_switch_active", "steps": results}
            if time.monotonic() >= deadline:
                return {"status": "aborted", "reason": "wall_clock_budget_exceeded", "steps": results}
            if any(not results[dep].get("success") for dep in step.depends_on):
                return {"status": "blocked", "reason": "dependency_failed", "steps": results}
            snapshot = self.perception.snapshot()
            foreground = snapshot.get("foreground_window") or {}
            memory = snapshot.get("memory") or {}
            battery = snapshot.get("battery") or {}
            observed_state = (
                foreground.get("handle"),
                foreground.get("pid"),
                bool(foreground.get("sensitive")),
                snapshot.get("process_count"),
                int(float(snapshot.get("cpu_percent", 0)) // 10),
                int(float(memory.get("percent", 0)) // 5) if memory else None,
                int(float(battery.get("percent", 0)) // 5) if battery else None,
            )
            argument_state = tuple(
                sorted((str(key), repr(value)) for key, value in step.args.items())
            )
            signature = repr((step.tool, argument_state, observed_state))
            self._seen_steps[signature] = self._seen_steps.get(signature, 0) + 1
            if self._seen_steps[signature] > 2:
                self.store.audit("plan_loop_detected", {
                    "goal": plan.goal,
                    "step_index": index,
                    "action": step.tool,
                })
                return {"status": "aborted", "reason": "loop_detected", "steps": results}
            try:
                resolved_args = self._resolve_previous_references(step.args, results)
            except ValueError as exc:
                return {"status": "blocked", "reason": str(exc), "steps": results}
            action_result = self.execute_action(
                step.tool, resolved_args, confirmed=confirmed, confidence=step.confidence,
                utterance=plan.goal, session_id=session_id,
            )
            if not action_result.success:
                action = self.registry.get(step.tool)
                retryable = action is not None and (
                    action.risk == RiskTier.READ_ONLY
                    or step.tool in {"volume.set", "window.minimize", "window.maximize", "window.restore"}
                )
                if retryable:
                    time.sleep(0.25)
                    action_result = self.execute_action(
                        step.tool, resolved_args, confirmed=confirmed, confidence=step.confidence,
                        utterance=plan.goal, session_id=session_id,
                    )
            from prixon.verifier import compare_expected
            expectation = compare_expected(
                step.expected_outcome,
                action_result.output,
                action=step.tool,
            )
            postconditions_verified = action_result.verified and expectation.verified
            item = {
                "index": index, "action": action_result.action,
                "success": action_result.success,
                "verified": postconditions_verified,
                "action_verified": action_result.verified,
                "expected_observed_verified": expectation.verified,
                "verification_reason": expectation.reason,
                "args": resolved_args,
                "output": action_result.output, "error": action_result.error,
                "undo_id": action_result.undo_id,
                "expected_outcome": step.expected_outcome,
                "prediction_error": expectation.prediction_error,
            }
            results.append(item)
            if not action_result.success:
                return {"status": "failed", "reason": action_result.error, "steps": results}
        return {"status": "completed", "steps": results}

    @staticmethod
    def _resolve_previous_references(
        args: dict[str, Any], results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resolved = dict(args)
        if not results:
            return resolved
        previous = results[-1].get("output", {})
        for key, value in list(resolved.items()):
            if isinstance(value, str) and value.startswith("$previous."):
                field = value.removeprefix("$previous.")
                if field not in previous or previous[field] is None:
                    raise ValueError(f"Previous step did not produce required reference: {field}")
                resolved[key] = previous[field]
        return resolved

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
