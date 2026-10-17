from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from prixon.consolidation import MacroPromoter
from prixon.events import (
    EventBus,
    FileSystemEventObserver,
    ProcessDeltaObserver,
    WinEventObserver,
    WinProcessTerminationObserver,
)
from prixon.kill_switch import GlobalHotkey
from prixon.schemas import AgentPlan
from prixon.store import AgentStore
from prixon.voice_kill import VoiceKillListener

logger = logging.getLogger(__name__)


def _focus_mode_enabled() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings",
        )
        value, _ = winreg.QueryValueEx(key, "NOC_GLOBAL_SETTING_TOASTS_ENABLED")
        return int(value) == 0
    except OSError:
        return False


def _fullscreen_active(hwnd: int | None) -> bool:
    if os.name != "nt" or not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    monitor = user32.MonitorFromWindow(hwnd, 2)
    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    area = info.rcMonitor
    return (
        abs(rect.left - area.left) <= 2 and abs(rect.top - area.top) <= 2
        and abs(rect.right - area.right) <= 2 and abs(rect.bottom - area.bottom) <= 2
    )


class AgentLoop:
    """Persistent bounded goal/event loop; proactive events remain suggestion-only."""

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.store: AgentStore = runtime.store
        self.bus = EventBus()
        self.process_observer = ProcessDeltaObserver(
            self.bus, interval_seconds=max(2.0, runtime.settings.agent_loop_poll_seconds),
        )
        self.window_observer = WinEventObserver(self.bus)
        self.file_observer = FileSystemEventObserver(self.bus)
        self.termination_observer = WinProcessTerminationObserver(self.bus)
        self.hotkey = GlobalHotkey(runtime.kill_switch)
        self.voice_kill = VoiceKillListener(
            runtime.kill_switch,
            enabled=runtime.settings.voice_kill_enabled,
            model_path=runtime.settings.voice_model_path,
            capture_seconds=runtime.settings.voice_capture_seconds,
        )
        self._last_consolidation = float(self.store.get_setting("learning.last_consolidation", 0))
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_battery_check = 0.0
        self._last_battery_low = False
        self._suggestions: list[dict[str, Any]] = []

    @property
    def running(self) -> bool:
        return self._running and bool(self._task and not self._task.done())

    def suggestions(self) -> list[dict[str, Any]]:
        return list(self._suggestions)

    def recover_interrupted_goals(self) -> int:
        interrupted = self.store.goals(("active",))
        for goal in interrupted:
            self.store.set_goal_status(goal["id"], "blocked")
            self.store.audit("goal_interrupted_by_restart", {
                "goal_id": goal["id"], "description": goal["description"],
            })
        return len(interrupted)

    def replay_persisted_events(self, limit: int = 500) -> int:
        events = self.store.pending_events(limit=limit)
        for event in events:
            self.bus.publish(
                event["event_type"], event["payload"], persisted_id=event["id"],
            )
        return len(events)

    async def start(self) -> dict[str, Any]:
        if self.running:
            return {"status": "already_running"}
        self.runtime.kill_switch.reset()
        self._running = True
        interrupted_count = self.recover_interrupted_goals()
        replayed_count = self.replay_persisted_events()
        await self.process_observer.start()
        self.window_observer.start()
        downloads_watched = self.file_observer.start()
        process_exit_observer = self.termination_observer.start()
        hotkey_registered = self.hotkey.start()
        voice_status = await asyncio.to_thread(self.voice_kill.start)
        self._task = asyncio.create_task(self._run(), name="PrixonAgentLoop")
        self.store.audit("agent_loop_started", {
            "global_hotkey_registered": hotkey_registered,
            "voice_kill": voice_status,
            "downloads_watched": downloads_watched,
            "process_exit_observer": process_exit_observer,
            "watched_folders": self.file_observer.watched_paths,
            "interrupted_goals": interrupted_count,
            "replayed_events": replayed_count,
        })
        return {
            "status": "started",
            "global_hotkey": "Ctrl+Alt+Pause" if hotkey_registered else "unavailable",
            "voice_kill": voice_status,
            "downloads_watched": downloads_watched,
            "process_exit_observer": process_exit_observer,
            "watched_folders": self.file_observer.watched_paths,
            "interrupted_goals": interrupted_count,
            "replayed_events": replayed_count,
        }

    async def stop(self, reason: str = "owner_requested") -> dict[str, Any]:
        self._running = False
        if self._task and self._task is not asyncio.current_task():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self.process_observer.stop()
        self.window_observer.stop()
        self.file_observer.stop()
        self.termination_observer.stop()
        self.hotkey.stop()
        await asyncio.to_thread(self.voice_kill.stop)
        self.store.audit("agent_loop_stopped", {"reason": reason})
        return {"status": "stopped", "reason": reason}

    async def _run(self) -> None:
        while self._running:
            if self.runtime.kill_switch.active:
                await self.stop(self.runtime.kill_switch.reason)
                return
            now = time.time()
            if now - self._last_battery_check >= 60:
                self._check_battery()
                self._last_battery_check = now
            for event in self.bus.drain(100):
                persisted_id = event.persisted_id or self.store.enqueue_event(
                    event.event_type, event.payload,
                )
                if event.event_type in {"file_created", "file_moved", "folder_created", "folder_moved"}:
                    path = event.payload.get("path")
                    if path:
                        target_path = Path(str(path))
                        kind = "folder" if event.payload.get("is_directory") else "file"
                        if target_path.exists():
                            self.runtime.index.refresh(kind, [{
                                "name": target_path.name, "target": str(target_path.resolve()),
                                "modified_at": event.payload.get("modified_at"),
                                "size_bytes": event.payload.get("size_bytes"),
                            }], source="filesystem_event")
                if event.event_type in {"file_deleted", "folder_deleted"}:
                    path = str(event.payload.get("path") or "")
                    if path:
                        self.store.remove_entity_target(path)
                if event.event_type == "window_destroyed":
                    handle = str(event.payload.get("hwnd") or "")
                    if handle:
                        self.runtime.index.remove_target("window", handle)
                        self.runtime.references.forget(handle)
                elif event.event_type == "window_created":
                    # Rebuild a bounded snapshot to pick up the new top-level HWND.
                    await asyncio.to_thread(self.runtime.refresh_entities, True)
                elif event.event_type == "foreground_changed":
                    if event.payload.get("sensitive"):
                        self.runtime.references.clear()
                    elif event.payload.get("hwnd") and event.payload.get("title"):
                        entity = {
                            "kind": "window", "name": event.payload["title"],
                            "target": str(event.payload["hwnd"]),
                            "hwnd": int(event.payload["hwnd"]),
                        }
                        self.runtime.references.remember(entity)
                        self.runtime.index.refresh("window", [{
                            "name": entity["name"], "target": entity["target"],
                            "handle": entity["hwnd"],
                        }])
                focus = _focus_mode_enabled()
                foreground = self.runtime.perception.snapshot().get("foreground_window")
                fullscreen = _fullscreen_active(
                    int(foreground["handle"]) if foreground and foreground.get("handle") else None
                )
                suggestion = self.runtime.proactive.evaluate(
                    event.event_type, event.payload,
                    focus_mode=focus, fullscreen=fullscreen,
                )
                if suggestion:
                    item = {
                        "trigger": suggestion.trigger, "title": suggestion.title,
                        "message": suggestion.message, "created_at": suggestion.created_at,
                        "score": suggestion.score,
                    }
                    self._suggestions.append(item)
                    self._suggestions = self._suggestions[-50:]
                self.store.mark_event_processed(persisted_id)
            self._emit_due_routines()
            if now - self._last_consolidation >= 86400:
                await self._run_consolidation(now)
            await asyncio.to_thread(self.runtime.process_pending_learning, 30)
            await self._continue_explicit_goals()
            await asyncio.sleep(max(0.5, self.runtime.settings.agent_loop_poll_seconds))

    def _emit_due_routines(self) -> int:
        now_local = __import__("datetime").datetime.now().astimezone()
        due = self.store.due_routines(now_local)
        for routine in due:
            self.bus.publish("routine_due", {
                "routine_id": routine["id"], "macro_id": routine["macro_id"],
                "title": routine["name"],
                "message": f"Your approved routine is scheduled for {routine['time_local']}. Review it before running.",
            }, persisted_id=routine["event_id"])
        return len(due)

    def _check_battery(self) -> None:
        try:
            battery = self.runtime.perception.snapshot().get("battery")
            if not battery:
                return
            low = float(battery["percent"]) <= 20 and not battery["plugged_in"]
            if low and not self._last_battery_low:
                self.bus.publish("battery_low", {"percent": battery["percent"]})
            self._last_battery_low = low
        except Exception:
            logger.exception("Battery event check failed")

    async def _run_consolidation(self, now: float) -> None:
        try:
            lexicon_result = self.runtime.lexicon.consolidate()
            macro_result = await asyncio.to_thread(
                MacroPromoter(self.store, self.runtime.registry).consolidate,
            )
            self._last_consolidation = now
            self.store.set_setting("learning.last_consolidation", now)
            self.store.audit("nightly_consolidation_finished", {
                "lexicon": lexicon_result, "macros_proposed": macro_result["count"],
            })
        except Exception:
            logger.exception("Nightly consolidation failed")

    async def _continue_explicit_goals(self) -> None:
        for goal in self.store.goals(("pending",)):
            payload = goal.get("payload") or {}
            raw_plan = payload.get("plan")
            if not raw_plan:
                continue
            try:
                plan = AgentPlan.model_validate(raw_plan)
                sensitive_actions = [
                    step.tool for step in plan.steps
                    if (
                        self.runtime.registry.get(step.tool)
                        and self.runtime.registry.get(step.tool).sensitive_output
                    )
                ]
                if sensitive_actions:
                    self.store.set_goal_status(goal["id"], "blocked")
                    self.store.audit("goal_blocked_interactive_sensitive_output", {
                        "goal_id": goal["id"],
                        "actions": sensitive_actions,
                        "reason": "sensitive output is limited to direct interactive requests",
                    })
                    continue
                self.store.set_goal_status(goal["id"], "active")
                result = await asyncio.to_thread(
                    self.runtime.executor.execute_plan, plan,
                    confirmed=bool(payload.get("confirmed", False)),
                )
                status = "completed" if result.get("status") == "completed" else "blocked"
                self.store.set_goal_status(goal["id"], status)
                self.store.episode(
                    goal["description"], ["goal_stack", "executor", "verifier"],
                    plan.model_dump(mode="json"), "success" if status == "completed" else "failure",
                    result.get("reason"),
                )
                self.store.audit("goal_execution_finished", {
                    "goal_id": goal["id"], "status": status,
                    "result": self.runtime._safe_execution_audit(result),
                })
            except Exception as exc:
                self.store.set_goal_status(goal["id"], "blocked")
                self.store.audit("goal_execution_error", {
                    "goal_id": goal["id"], "error": f"{type(exc).__name__}:{exc}",
                })
