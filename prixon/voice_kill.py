from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable

from prixon.kill_switch import KillSwitch


class VoiceKillListener:
    """Local Vosk push-to-talk listener for emergency kill and ordinary commands.

    The microphone is opened only after Ctrl+Alt+V or Ctrl+Alt+M. Audio and the
    recognized transcript are held in memory only; there is no cloud fallback.
    """

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    VK_V = 0x56
    VK_M = 0x4D
    KILL_HOTKEY_ID = 0xA1F
    COMMAND_HOTKEY_ID = 0xA20
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    SAMPLE_RATE = 16000
    BLOCK_SIZE = 4000

    KILL_GRAMMAR = [
        "prix on stop", "prixon stop", "prix on halt", "prixon halt",
        "prix on abort", "prixon abort", "prix on emergency stop",
        "prixon emergency stop", "pryson stop", "price on stop", "[unk]",
    ]
    KILL_PHRASES = {
        "prix on stop", "prixon stop", "prix on halt", "prixon halt",
        "prix on abort", "prixon abort", "prix on emergency stop",
        "prixon emergency stop", "pryson stop", "price on stop",
    }

    def __init__(
        self,
        kill_switch: KillSwitch,
        *,
        enabled: bool = False,
        model_path: str = "",
        capture_seconds: float = 5.0,
        command_enabled: bool = False,
        command_capture_seconds: float = 7.0,
        on_command: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        self.kill_switch = kill_switch
        self.enabled = bool(enabled)
        self.command_enabled = bool(command_enabled)
        self.model_path = model_path
        self.capture_seconds = max(2.0, min(float(capture_seconds), 8.0))
        self.command_capture_seconds = max(3.0, min(float(command_capture_seconds), 10.0))
        self.on_command = on_command
        self._model = None
        self._sounddevice = None
        self._recognizer_type = None
        self._thread: threading.Thread | None = None
        self._capture_thread: threading.Thread | None = None
        self._stream = None
        self._stream_lock = threading.Lock()
        self._started = threading.Event()
        self._stop = threading.Event()
        self._capture_lock = threading.Lock()
        self._capturing = threading.Event()
        self._thread_id: int | None = None
        self._kill_registered = False
        self._command_registered = False
        self._last_result = "not_started"
        self._last_command_status: str | None = None
        self._last_command_action: str | None = None
        self._error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self._model is not None and (
                self._kill_registered or self._command_registered
            ),
            "kill_hotkey": "Ctrl+Alt+V" if self._kill_registered else None,
            "command_hotkey": "Ctrl+Alt+M" if self._command_registered else None,
            "command_enabled": self.command_enabled,
            "listening": self._capturing.is_set(),
            "last_result": self._last_result,
            "last_command_status": self._last_command_status,
            "last_command_action": self._last_command_action,
            "error": self._error,
            "mode": "push_to_talk_local_only",
        }

    def start(self) -> dict[str, Any]:
        if not self.enabled and not self.command_enabled:
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
        if self._thread and self._thread.is_alive() and (
            self._kill_registered or self._command_registered
        ):
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
            target=self._hotkey_loop, name="PrixonVoiceHotkeys", daemon=True,
        )
        self._thread.start()
        self._started.wait(timeout=2)
        if not self._started.is_set():
            self._error = "voice_hotkey_start_timeout"
        elif not (self._kill_registered or self._command_registered):
            self._error = "voice_hotkeys_unavailable"
        else:
            self._error = None
            self._last_result = "ready"
        return self.status()

    def stop(self) -> None:
        self._stop.set()
        with self._stream_lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if self._thread_id and os.name == "nt":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
        if self._capture_thread:
            self._capture_thread.join(timeout=2)
        self._thread = None
        self._capture_thread = None
        self._kill_registered = False
        self._command_registered = False

    def _hotkey_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        if self.enabled:
            self._kill_registered = bool(user32.RegisterHotKey(
                None, self.KILL_HOTKEY_ID,
                self.MOD_CONTROL | self.MOD_ALT, self.VK_V,
            ))
        if self.command_enabled:
            self._command_registered = bool(user32.RegisterHotKey(
                None, self.COMMAND_HOTKEY_ID,
                self.MOD_CONTROL | self.MOD_ALT, self.VK_M,
            ))
        self._started.set()
        message = wintypes.MSG()
        try:
            while not self._stop.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message != self.WM_HOTKEY or self.kill_switch.active:
                    continue
                if message.wParam == self.KILL_HOTKEY_ID and self._kill_registered:
                    mode = "kill"
                    duration = self.capture_seconds
                elif message.wParam == self.COMMAND_HOTKEY_ID and self._command_registered:
                    mode = "command"
                    duration = self.command_capture_seconds
                else:
                    continue
                if not self._capturing.is_set():
                    self._capture_thread = threading.Thread(
                        target=self._capture_phrase,
                        args=(mode, duration),
                        name=f"PrixonVoiceCapture-{mode}",
                        daemon=True,
                    )
                    self._capture_thread.start()
        finally:
            if self._kill_registered:
                user32.UnregisterHotKey(None, self.KILL_HOTKEY_ID)
            if self._command_registered:
                user32.UnregisterHotKey(None, self.COMMAND_HOTKEY_ID)
            self._kill_registered = False
            self._command_registered = False

    @staticmethod
    def _normalize_phrase(value: str) -> str:
        value = re.sub(r"[^a-z0-9 ]", " ", value.casefold())
        return re.sub(r"\s+", " ", value).strip()

    def _speak_local(self, text: str) -> None:
        if os.name != "nt" or not text:
            return
        initialized = False
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            initialized = True
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text[:240], 1)
        except Exception:
            # Voice output is optional; command execution/status remains available by API.
            return
        finally:
            if initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _capture_phrase(self, mode: str, duration: float) -> None:
        if not self._capture_lock.acquire(blocking=False):
            return
        self._capturing.set()
        self._last_result = "listening_for_kill" if mode == "kill" else "listening_for_command"
        try:
            grammar = json.dumps(self.KILL_GRAMMAR) if mode == "kill" else None
            if grammar:
                recognizer = self._recognizer_type(
                    self._model, self.SAMPLE_RATE, grammar,
                )
            else:
                recognizer = self._recognizer_type(self._model, self.SAMPLE_RATE)
            recognized: list[str] = []
            deadline = time.monotonic() + duration
            stream = self._sounddevice.RawInputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=self.BLOCK_SIZE,
                dtype="int16",
                channels=1,
            )
            with self._stream_lock:
                self._stream = stream
            try:
                with stream:
                    while time.monotonic() < deadline and not self._stop.is_set():
                        audio, _overflowed = stream.read(self.BLOCK_SIZE)
                        if recognizer.AcceptWaveform(audio):
                            recognized.append(str(json.loads(recognizer.Result()).get("text", "")))
            finally:
                with self._stream_lock:
                    if self._stream is stream:
                        self._stream = None
            final = json.loads(recognizer.FinalResult())
            recognized.append(str(final.get("text", "")))
            phrase = self._normalize_phrase(" ".join(recognized))
            if mode == "kill":
                matched = any(
                    phrase == command or phrase.endswith(" " + command)
                    for command in self.KILL_PHRASES
                )
                if matched:
                    self._last_result = "kill_phrase_recognized"
                    self.kill_switch.trigger("voice_kill_phrase")
                else:
                    self._last_result = "no_kill_phrase"
                return
            if not phrase:
                self._last_result = "no_command_recognized"
                return
            if any(
                phrase == command or phrase.endswith(" " + command)
                for command in self.KILL_PHRASES
            ):
                self._last_result = "kill_phrase_recognized"
                self.kill_switch.trigger("voice_kill_phrase")
                return
            if self.on_command is None:
                self._last_result = "command_handler_unavailable"
                return
            result = self.on_command(phrase) or {}
            self._last_command_status = str(result.get("status") or "unknown")
            action = result.get("action")
            self._last_command_action = str(action) if action else None
            spoken = str(result.get("spoken_response") or "")
            self._speak_local(spoken)
            self._last_result = "command_processed"
        except Exception as exc:
            self._last_result = "capture_failed"
            self._error = f"voice_capture_error:{type(exc).__name__}"
        finally:
            with self._stream_lock:
                self._stream = None
            self._capturing.clear()
            self._capture_lock.release()
