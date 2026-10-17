from __future__ import annotations

import os
import threading


class KillSwitch:
    """Thread-safe cancellation token shared by the planner and executor."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason = "not_requested"

    def trigger(self, reason: str = "owner_requested") -> None:
        self._reason = reason
        self._event.set()

    def reset(self) -> None:
        self._reason = "not_requested"
        self._event.clear()

    @property
    def active(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def check(self) -> None:
        if self.active:
            raise RuntimeError(f"Agent halted: {self._reason}")


class GlobalHotkey:
    """Registers Ctrl+Alt+Pause on Windows and triggers the shared kill switch."""

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    VK_PAUSE = 0x13
    HOTKEY_ID = 0xA1E

    def __init__(self, kill_switch: KillSwitch) -> None:
        self.kill_switch = kill_switch
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._thread_id: int | None = None

    def start(self) -> bool:
        if os.name != "nt":
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._started.clear()
        self._thread = threading.Thread(target=self._run, name="PrixonKillHotkey", daemon=True)
        self._thread.start()
        self._started.wait(timeout=2)
        return self._started.is_set()

    def stop(self) -> None:
        if self._thread_id and os.name == "nt":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(
            None, self.HOTKEY_ID, self.MOD_CONTROL | self.MOD_ALT, self.VK_PAUSE,
        ):
            self._started.set()
            return
        self._started.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312 and message.wParam == self.HOTKEY_ID:
                    self.kill_switch.trigger("global_hotkey_ctrl_alt_pause")
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
