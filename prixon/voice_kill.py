from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from prixon.kill_switch import KillSwitch


class VoiceKillListener:
    """Push-to-listen, local-only voice kill phrase recognizer.

    Audio is captured only after Ctrl+Alt+V, processed in memory by Vosk, and
    discarded. No audio or transcript is persisted, and there is no cloud fallback.
    """

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    VK_V = 0x56
    HOTKEY_ID = 0xA1F
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    SAMPLE_RATE = 16000
    BLOCK_SIZE = 4000

    GRAMMAR = [
        "prix on stop", "prixon stop",
        "prix on halt", "prixon halt",
        "prix on abort", "prixon abort",
        "prix on emergency stop", "prixon emergency stop",
        "[unk]",
    ]
    KILL_PHRASES = {
        "prix on stop", "prixon stop",
        "prix on halt", "prixon halt",
        "prix on abort", "prixon abort",
        "prix on emergency stop", "prixon emergency stop",
    }

    def __init__(
        self,
        kill_switch: KillSwitch,
        *,
        enabled: bool = False,
        model_path: str = "",
        capture_seconds: float = 5.0,
    ) -> None:
        self.kill_switch = kill_switch
        self.enabled = bool(enabled)
        self.model_path = model_path
        self.capture_seconds = max(2.0, min(float(capture_seconds), 8.0))
        self._model = None
        self._sounddevice = None
        self._recognizer_type = None
        self._thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None
        self._started = threading.Event()
        self._stop = threading.Event()
        self._capture_lock = threading.Lock()
        self._capturing = threading.Event()
        self._thread_id: int | None = None
        self._registered = False
        self._last_result = "not_started"
        self._error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self._registered and self._model is not None,
            "hotkey": "Ctrl+Alt+V" if self._registered else None,
            "listening": self._capturing.is_set(),
            "last_result": self._last_result,
            "error": self._error,
            "mode": "push_to_listen_local_only",
        }

    def start(self) -> dict[str, Any]:
        if not self.enabled:
            self._last_result = "disabled"
            return self.status()
        if os.name != "nt":
            self._error = "windows_only"
            return self.status()
        if not self.model_path.strip():
            self._error = "local_vosk_model_path_not_configured"
            return self.status()
        model_path = Path(self.model_path).expanduser()
        if not model_path.is_dir():
            self._error = "local_vosk_model_directory_missing"
            return self.status()
        if self._thread and self._thread.is_alive() and self._registered:
            return self.status()
        try:
            import sounddevice
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)
            self._sounddevice = sounddevice
            self._model = Model(str(model_path.resolve()))
            self._recognizer_type = KaldiRecognizer
        except Exception as exc:
            self._error = f"local_voice_dependencies_unavailable:{type(exc).__name__}"
            self._model = None
            return self.status()

        self._started.clear()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._hotkey_loop, name="PrixonVoiceKillHotkey", daemon=True,
        )
        self._thread.start()
        self._started.wait(timeout=2)
        if not self._started.is_set():
            self._error = "voice_hotkey_start_timeout"
        elif not self._registered:
            self._error = "voice_hotkey_unavailable"
        else:
            self._error = None
            self._last_result = "ready"
        return self.status()

    def stop(self) -> None:
        self._stop.set()
        if self._thread_id and os.name == "nt":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
        if self._capture_thread:
            self._capture_thread.join(timeout=2)
        self._thread = None
        self._capture_thread = None
        self._registered = False

    def _hotkey_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(
            None, self.HOTKEY_ID,
            self.MOD_CONTROL | self.MOD_ALT,
            self.VK_V,
        ):
            self._started.set()
            return
        self._registered = True
        self._started.set()
        message = wintypes.MSG()
        try:
            while not self._stop.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message == self.WM_HOTKEY and message.wParam == self.HOTKEY_ID:
                    if not self._capturing.is_set() and not self.kill_switch.active:
                        self._capture_thread = threading.Thread(
                            target=self._capture_phrase,
                            name="PrixonVoiceKillCapture",
                            daemon=True,
                        )
                        self._capture_thread.start()
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False

    @staticmethod
    def _normalize_phrase(value: str) -> str:
        value = re.sub(r"[^a-z ]", " ", value.casefold())
        return re.sub(r"\s+", " ", value).strip()

    def _capture_phrase(self) -> None:
        if not self._capture_lock.acquire(blocking=False):
            return
        self._capturing.set()
        self._last_result = "listening"
        try:
            recognizer = self._recognizer_type(
                self._model, self.SAMPLE_RATE, json.dumps(self.GRAMMAR),
            )
            recognized: list[str] = []
            deadline = time.monotonic() + self.capture_seconds
            with self._sounddevice.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                dtype="int16",
                channels=1,
            ) as stream:
                while time.monotonic() < deadline and not self._stop.is_set():
                    audio, _overflowed = stream.read(self.BLOCK_SIZE)
                    if recognizer.AcceptWaveform(audio):
                        recognized.append(str(json.loads(recognizer.Result()).get("text", "")))
            final = json.loads(recognizer.FinalResult())
            recognized.append(str(final.get("text", "")))
            phrase = self._normalize_phrase(" ".join(recognized))
            matched = any(
                phrase == command or phrase.endswith(" " + command)
                for command in self.KILL_PHRASES
            )
            if matched:
                self._last_result = "kill_phrase_recognized"
                self.kill_switch.trigger("voice_kill_phrase")
            else:
                self._last_result = "no_kill_phrase"
        except Exception as exc:
            self._last_result = "capture_failed"
            self._error = f"voice_capture_error:{type(exc).__name__}"
        finally:
            self._capturing.clear()
            self._capture_lock.release()
