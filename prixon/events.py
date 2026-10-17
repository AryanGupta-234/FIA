from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import psutil


@dataclass(frozen=True)
class AgentEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class EventBus:
    def __init__(self, max_queue: int = 1000) -> None:
        self._queue: deque[AgentEvent] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[AgentEvent], None]] = []

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> AgentEvent:
        event = AgentEvent(event_type, payload or {})
        with self._lock:
            self._queue.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                continue
        return event

    def drain(self, limit: int = 100) -> list[AgentEvent]:
        with self._lock:
            events = [self._queue.popleft() for _ in range(min(limit, len(self._queue)))]
        return events

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._queue)


class ProcessDeltaObserver:
    """Bounded process-start/stop fallback observer using lightweight psutil snapshots."""

    def __init__(self, bus: EventBus, interval_seconds: float = 2.0) -> None:
        self.bus = bus
        self.interval_seconds = max(1.0, interval_seconds)
        self._previous: dict[tuple[int, str], dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._previous = await asyncio.to_thread(self._snapshot)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @staticmethod
    def _snapshot() -> dict[tuple[int, str], dict[str, Any]]:
        current = {}
        for process in psutil.process_iter(["pid", "name"]):
            try:
                info = process.info
                key = (int(info["pid"]), str(info.get("name") or ""))
                current[key] = {"pid": key[0], "name": key[1]}
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return current

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self.interval_seconds)
            current = await asyncio.to_thread(self._snapshot)
            for key in current.keys() - self._previous.keys():
                self.bus.publish("process_started", current[key])
            for key in self._previous.keys() - current.keys():
                self.bus.publish("process_stopped", {"pid": key[0], "name": key[1]})
            self._previous = current


class WinEventObserver:
    """Uses SetWinEventHook for foreground and window lifecycle events on Windows."""

    EVENT_SYSTEM_FOREGROUND = 0x0003
    EVENT_OBJECT_CREATE = 0x8000
    EVENT_OBJECT_DESTROY = 0x8001
    WINEVENT_OUTOFCONTEXT = 0x0000
    WM_QUIT = 0x0012

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._thread_id: int | None = None
        self.available = os.name == "nt"

    def start(self) -> None:
        if not self.available or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._message_loop, name="PrixonWinEvents", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread_id and os.name == "nt":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def _message_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        callback_type = ctypes.WINFUNCTYPE(
            None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
            wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
        )

        def callback(_hook, event, hwnd, object_id, child_id, _thread, _ms):
            if not hwnd:
                return
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            event_name = {
                self.EVENT_SYSTEM_FOREGROUND: "foreground_changed",
                self.EVENT_OBJECT_CREATE: "window_created",
                self.EVENT_OBJECT_DESTROY: "window_destroyed",
            }.get(int(event), "window_event")
            payload = {"hwnd": int(hwnd), "pid": int(pid.value),
                       "object_id": int(object_id), "child_id": int(child_id)}
            if event == self.EVENT_SYSTEM_FOREGROUND:
                length = user32.GetWindowTextLengthW(hwnd)
                title = ctypes.create_unicode_buffer(min(length + 1, 512))
                user32.GetWindowTextW(hwnd, title, len(title))
                payload["title"] = title.value[:500]
            self.bus.publish(event_name, payload)

        callback_ref = callback_type(callback)
        hooks = []
        for event_id in (
            self.EVENT_SYSTEM_FOREGROUND, self.EVENT_OBJECT_CREATE, self.EVENT_OBJECT_DESTROY,
        ):
            hook = user32.SetWinEventHook(
                event_id, event_id, 0, callback_ref, 0, 0, self.WINEVENT_OUTOFCONTEXT,
            )
            if hook:
                hooks.append(hook)
        message = wintypes.MSG()
        while not self._stop.is_set() and user32.GetMessageW(ctypes.byref(message), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        for hook in hooks:
            user32.UnhookWinEvent(hook)


class FileSystemEventObserver:
    """Watches Downloads for completed files; contents are never read."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._observer = None
        self.available = False

    def start(self) -> bool:
        if os.name != "nt":
            return False
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return False
        downloads = Path.home() / "Downloads"
        if not downloads.exists():
            return False
        bus = self.bus

        class Handler(FileSystemEventHandler):
            def _stable(self, path_value: str) -> None:
                path = Path(path_value)
                if not path.is_file():
                    return
                previous = -1
                stable = 0
                for _ in range(8):
                    time.sleep(0.5)
                    try:
                        current = path.stat().st_size
                    except OSError:
                        return
                    stable = stable + 1 if current == previous else 0
                    previous = current
                    if stable >= 2:
                        bus.publish("download_finished", {
                            "name": path.name[:180], "size_bytes": current,
                        })
                        return

            def on_created(self, event):
                if not event.is_directory:
                    threading.Thread(target=self._stable, args=(event.src_path,), daemon=True).start()

            def on_moved(self, event):
                if not event.is_directory:
                    threading.Thread(target=self._stable, args=(event.dest_path,), daemon=True).start()

        observer = Observer()
        observer.schedule(Handler(), str(downloads), recursive=False)
        observer.start()
        self._observer = observer
        self.available = True
        return True

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        self.available = False
