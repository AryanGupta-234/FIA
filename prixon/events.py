from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil


class WindowsPerceptionTitleFilter:
    SENSITIVE_TERMS = (
        "password", "credential", "sign in", "sign-in", "log in", "login",
        "windows security", "security key", "authentication", "authenticator",
        "two-factor", "2fa", "pin entry",
    )


@dataclass(frozen=True)
class AgentEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    persisted_id: int | None = None


class EventBus:
    def __init__(self, max_queue: int = 1000) -> None:
        self._queue: deque[AgentEvent] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[AgentEvent], None]] = []

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def publish(
        self, event_type: str, payload: dict[str, Any] | None = None,
        *, persisted_id: int | None = None,
    ) -> AgentEvent:
        event = AgentEvent(event_type, payload or {}, persisted_id=persisted_id)
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
                raw_title = title.value[:500]
                sensitive_terms = WindowsPerceptionTitleFilter.SENSITIVE_TERMS
                if any(term in raw_title.casefold() for term in sensitive_terms):
                    payload["title"] = None
                    payload["sensitive"] = True
                else:
                    payload["title"] = raw_title
                    payload["sensitive"] = False
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


class WinProcessTerminationObserver:
    """Optional WMI process-stop observer that distinguishes non-zero exits."""

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.available = os.name == "nt"

    def start(self) -> bool:
        if not self.available:
            return False
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError:
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="PrixonProcessTermination", daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    @staticmethod
    def classify_stop(process_name: str, process_id: int, exit_status: int) -> tuple[str, dict[str, Any]]:
        event_type = "process_crashed" if exit_status != 0 else "process_stopped"
        return event_type, {
            "name": process_name[:180],
            "pid": int(process_id),
            "exit_status": int(exit_status),
            "unexpected": exit_status != 0,
        }

    def _run(self) -> None:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            service = win32com.client.GetObject(r"winmgmts:\\.\root\cimv2")
            watcher = service.ExecNotificationQuery(
                "SELECT * FROM Win32_ProcessStopTrace"
            )
            while not self._stop.is_set():
                try:
                    event = watcher.NextEvent(2000)
                except pythoncom.com_error:
                    continue
                try:
                    payload = self.classify_stop(
                        str(event.ProcessName),
                        int(event.ProcessID),
                        int(event.ExitStatus),
                    )
                    self.bus.publish(payload[0], payload[1])
                except (AttributeError, TypeError, ValueError):
                    continue
        except Exception:
            # WMI is an optional observer; the psutil delta observer remains active.
            return
        finally:
            pythoncom.CoUninitialize()


class FileSystemEventObserver:
    """Watches known user folders for file changes; never reads file contents."""

    WATCHED_FOLDERS = ("Downloads", "Documents", "Desktop")

    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._observers: list[Any] = []
        self.available = False
        self.watched_paths: list[str] = []

    def start(self) -> bool:
        if os.name != "nt":
            return False
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return False
        roots = [
            Path.home() / name for name in self.WATCHED_FOLDERS
            if (Path.home() / name).is_dir()
        ]
        if not roots:
            return False
        bus = self.bus

        class Handler(FileSystemEventHandler):
            def _payload(self, path_value: str) -> dict[str, Any] | None:
                path = Path(path_value)
                try:
                    stat = path.stat()
                except OSError:
                    return None
                return {
                    "name": path.name[:180],
                    "path": str(path.resolve()),
                    "is_directory": path.is_dir(),
                    "size_bytes": int(stat.st_size) if path.is_file() else None,
                    "modified_at": float(stat.st_mtime),
                }

            def _stable_download(self, path_value: str) -> None:
                path = Path(path_value)
                if path.suffix.casefold() in {".crdownload", ".part", ".tmp", ".download"}:
                    return
                if not path.is_file():
                    return
                previous = -1
                stable = 0
                for _ in range(8):
                    if not path.exists():
                        return
                    time.sleep(0.5)
                    try:
                        current = path.stat().st_size
                    except OSError:
                        return
                    stable = stable + 1 if current == previous else 0
                    previous = current
                    if stable >= 2:
                        payload = self._payload(str(path))
                        if payload:
                            bus.publish("download_finished", payload)
                        return

            def on_created(self, event):
                payload = self._payload(event.src_path)
                if payload:
                    bus.publish(
                        "folder_created" if event.is_directory else "file_created",
                        payload,
                    )
                if not event.is_directory and Path(event.src_path).parent.name.casefold() == "downloads":
                    threading.Thread(
                        target=self._stable_download, args=(event.src_path,), daemon=True,
                    ).start()

            def on_modified(self, event):
                if event.is_directory:
                    return
                payload = self._payload(event.src_path)
                if payload:
                    bus.publish("file_modified", payload)

            def on_moved(self, event):
                payload = self._payload(event.dest_path)
                if payload:
                    bus.publish("folder_moved" if event.is_directory else "file_moved", payload)
                if not event.is_directory and Path(event.dest_path).parent.name.casefold() == "downloads":
                    threading.Thread(
                        target=self._stable_download, args=(event.dest_path,), daemon=True,
                    ).start()

            def on_deleted(self, event):
                path = Path(event.src_path)
                bus.publish(
                    "folder_deleted" if event.is_directory else "file_deleted",
                    {"name": path.name[:180], "path": str(path)},
                )

        self.stop()
        for root in roots:
            observer = Observer()
            observer.schedule(Handler(), str(root), recursive=True)
            observer.start()
            self._observers.append(observer)
            self.watched_paths.append(str(root))
        self.available = bool(self._observers)
        return self.available

    def stop(self) -> None:
        for observer in self._observers:
            observer.stop()
        for observer in self._observers:
            observer.join(timeout=2)
        self._observers.clear()
        self.watched_paths.clear()
        self.available = False
