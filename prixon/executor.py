from __future__ import annotations

import os
import shutil
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import psutil

from prixon.governance import decide
from prixon.perception import WindowsPerception
from prixon.registry import ActionRegistry
from prixon.schemas import AgentPlan, PlanStep, RiskTier
from prixon.store import AgentStore


@dataclass
class ExecutionBudget:
    max_steps: int = 8
    max_replans: int = 2
    wall_clock_seconds: float = 60.0
    max_model_tokens: int = 1024
    step_timeout_seconds: float = 12.0
    max_actions_per_minute: int = 30


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
                "connections": len(psutil.net_connections(kind="inet")),
            }
        if action == "app.launch":
            self._require_windows()
            target = str(args.get("application_target", ""))
            self._validate_launch_target(target)
            before_pids = set(psutil.pids())
            os.startfile(target)  # type: ignore[attr-defined]
            time.sleep(0.5)
            selected_pid = None
            app_name = str(args.get("application") or "").casefold()
            process_hints = {
                "paint": ("mspaint.exe",),
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
            foreground = None
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and selected_pid is None:
                foreground = self.perception._foreground_window()
                candidates = sorted(set(psutil.pids()) - before_pids)
                for pid in candidates:
                    try:
                        process_name = psutil.Process(pid).name().casefold()
                        if any(hint in process_name for hint in hints):
                            selected_pid = pid
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                if (
                    selected_pid is None and foreground and not foreground.get("sensitive")
                    and foreground.get("pid")
                ):
                    try:
                        foreground_name = psutil.Process(int(foreground["pid"])).name().casefold()
                        if any(hint in foreground_name for hint in hints):
                            selected_pid = int(foreground["pid"])
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if selected_pid is None:
                    time.sleep(0.2)
            if foreground and foreground.get("sensitive"):
                foreground = None
            return {
                "launched": target, "application": args.get("application"),
                "pid": selected_pid,
                "hwnd": foreground.get("handle") if foreground and not foreground.get("sensitive") and selected_pid and foreground.get("pid") == selected_pid else None,
                "window": foreground.get("title") if foreground and not foreground.get("sensitive") and selected_pid and foreground.get("pid") == selected_pid else None,
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
            time.sleep(0.5)
            foreground = self.perception._foreground_window()
            return {"opened_setting": setting, "uri": uri,
                    "hwnd": foreground.get("handle") if foreground else None}
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
                from ctypes import wintypes
                left, top, right, bottom = before["rect"]
                user32.SetWindowPos(
                    hwnd, 0, left, top, right - left, bottom - top,
                    0x0004 | 0x0010,
                )
            return True
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

    def execute_action(
        self, action_name: str, args: dict[str, Any], *,
        confirmed: bool = False, confidence: float = 1.0,
    ) -> ActionResult:
        action = self.registry.get(action_name)
        if action is None:
            return ActionResult(False, action_name, error="unknown_action")
        if self.kill_switch and self.kill_switch.active:
            return ActionResult(False, action_name, error="kill_switch_active")
        now = time.monotonic()
        while self._action_times and now - self._action_times[0] >= 60:
            self._action_times.popleft()
        if len(self._action_times) >= self.budget.max_actions_per_minute:
            return ActionResult(False, action_name, error="action_rate_limit_exceeded")
        self._action_times.append(now)
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
        if action.risk != RiskTier.READ_ONLY and not action.undo_supported and action.risk != RiskTier.ALWAYS_CONFIRM:
            return ActionResult(False, action_name, error="state_change_without_undo_recipe_blocked")

        try:
            before = self.adapters.capture_before(action_name, args)
        except Exception as exc:
            return ActionResult(False, action_name, error=f"precondition_failed:{type(exc).__name__}:{exc}")
        undo_id = None
        if action.risk != RiskTier.READ_ONLY:
            undo_id = self.store.record_undo(action_name, args, before)
        future = self._executor.submit(self.adapters.execute, action_name, args)
        try:
            output = future.result(timeout=self.budget.step_timeout_seconds)
        except TimeoutError:
            self.store.audit("action_timeout", {"action": action_name, "args": args})
            if undo_id:
                self.store.finish_undo(undo_id, "failed")
            return ActionResult(False, action_name, error="action_timeout", undo_id=undo_id)
        except Exception as exc:
            self.store.audit("action_failed", {"action": action_name, "error": str(exc)})
            if undo_id:
                self.store.finish_undo(undo_id, "failed")
            return ActionResult(False, action_name, error=f"{type(exc).__name__}:{exc}", undo_id=undo_id)

        verified = self.verify(action_name, args, output)
        if undo_id:
            self.store.update_undo_output(undo_id, output)
        if not verified:
            self.store.audit("verification_failed", {"action": action_name, "output": output})
            if undo_id:
                try:
                    rolled_back = self.adapters.undo(action_name, args, before, output)
                except Exception:
                    rolled_back = False
                self.store.finish_undo(undo_id, "undone" if rolled_back else "failed")
            return ActionResult(False, action_name, output, "postcondition_failed", undo_id, False)
        self.store.audit("action_completed", {
            "action": action_name, "args": args, "output": output, "undo_id": undo_id,
        })
        return ActionResult(True, action_name, output, undo_id=undo_id, verified=True)

    def verify(self, action_name: str, args: dict[str, Any], output: dict[str, Any]) -> bool:
        if action_name in {
            "system.status", "process.list", "system.battery", "system.network",
            "system.memory", "system.cpu", "system.wifi", "system.audio",
        }:
            return bool(output)
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
            return bool(output.get("opened_setting"))
        if action_name == "file.quarantine":
            return Path(output.get("quarantined_path", "")).is_file()
        return False

    def execute_plan(self, plan: AgentPlan, *, confirmed: bool = False) -> dict[str, Any]:
        started = time.monotonic()
        self._seen_steps.clear()
        from prixon.planner import validate_plan
        validation = validate_plan(plan, self.registry, self.budget.max_steps)
        if not validation.valid:
            return {
                "status": "rejected", "reason": "plan_validation_failed",
                "errors": validation.errors, "steps": [],
            }
        results: list[dict[str, Any]] = []
        for index, step in enumerate(plan.steps):
            if self.kill_switch and self.kill_switch.active:
                return {"status": "aborted", "reason": "kill_switch_active", "steps": results}
            if time.monotonic() - started > self.budget.wall_clock_seconds:
                return {"status": "aborted", "reason": "wall_clock_budget_exceeded", "steps": results}
            if any(not results[dep].get("success") for dep in step.depends_on):
                return {"status": "blocked", "reason": "dependency_failed", "steps": results}
            signature = f"{step.tool}|{sorted(step.args.items())}"
            self._seen_steps[signature] = self._seen_steps.get(signature, 0) + 1
            if self._seen_steps[signature] > 2:
                return {"status": "aborted", "reason": "loop_detected", "steps": results}
            try:
                resolved_args = self._resolve_previous_references(step.args, results)
            except ValueError as exc:
                return {"status": "blocked", "reason": str(exc), "steps": results}
            action_result = self.execute_action(
                step.tool, resolved_args, confirmed=confirmed, confidence=step.confidence,
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
                    )
            item = {
                "index": index, "action": action_result.action,
                "success": action_result.success, "verified": action_result.verified,
                "args": resolved_args,
                "output": action_result.output, "error": action_result.error,
                "undo_id": action_result.undo_id,
                "expected_outcome": step.expected_outcome,
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
