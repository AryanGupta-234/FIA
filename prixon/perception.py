from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from typing import Any

import psutil


class WindowsPerception:
    """Compact, privacy-bounded machine observations.

    Does not read page text, URLs, cookies, passwords, form values or credential dialogs.
    Sensitive foreground window titles are discarded before entering the world model.
    """

    SENSITIVE_TITLE_TERMS = (
        "password", "credential", "sign in", "sign-in", "log in", "login",
        "windows security", "security key", "authentication", "authenticator",
        "two-factor", "2fa", "pin entry",
    )

    @classmethod
    def _is_sensitive_title(cls, title: str) -> bool:
        value = title.casefold()
        return any(term in value for term in cls.SENSITIVE_TITLE_TERMS)

    @staticmethod
    def _foreground_window() -> dict[str, Any] | None:
        if os.name != "nt":
            return None
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(min(length + 1, 512))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = buffer.value[:500]
        sensitive = WindowsPerception._is_sensitive_title(title)
        return {
            "handle": int(hwnd),
            "title": None if sensitive else title,
            "pid": int(pid.value),
            "sensitive": sensitive,
        }

    @staticmethod
    def _installed_apps() -> list[dict[str, str]]:
        if os.name != "nt":
            return []
        roots = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        apps: dict[str, str] = {}
        for root in roots:
            if not root.exists():
                continue
            try:
                for shortcut in root.rglob("*.lnk"):
                    name = shortcut.stem.strip()
                    if name and name.casefold() not in apps:
                        apps[name.casefold()] = str(shortcut)
            except OSError:
                continue
        return [{"name": name, "target": target} for name, target in apps.items()]

    def processes(self, limit: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for process in psutil.process_iter(["pid", "name", "exe", "status"]):
            try:
                item = process.info
                rows.append({
                    "pid": int(item["pid"]),
                    "name": str(item.get("name") or ""),
                    "exe": item.get("exe"),
                    "status": str(item.get("status") or ""),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            if len(rows) >= limit:
                break
        return rows

    def snapshot(self) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        try:
            battery = psutil.sensors_battery()
            battery_state = None if battery is None else {
                "percent": round(float(battery.percent), 1),
                "plugged_in": bool(battery.power_plugged),
                "seconds_left": battery.secsleft if battery.secsleft >= 0 else None,
            }
        except (AttributeError, OSError):
            battery_state = None
        try:
            network = psutil.net_io_counters()
            network_state = {
                "bytes_sent": int(network.bytes_sent),
                "bytes_received": int(network.bytes_recv),
            }
        except (AttributeError, OSError):
            network_state = None
        return {
            "platform": platform.platform(),
            "is_windows": os.name == "nt",
            "captured_at": time.time(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": {
                "total_bytes": int(memory.total),
                "available_bytes": int(memory.available),
                "percent": float(memory.percent),
            },
            "battery": battery_state,
            "network": network_state,
            "foreground_window": self._foreground_window(),
            "process_count": len(psutil.pids()),
        }

    def installed_apps(self) -> list[dict[str, str]]:
        return self._installed_apps()

    @staticmethod
    def known_folders() -> list[dict[str, str]]:
        roots = [
            ("Desktop", Path.home() / "Desktop"),
            ("Documents", Path.home() / "Documents"),
            ("Downloads", Path.home() / "Downloads"),
            ("Pictures", Path.home() / "Pictures"),
        ]
        known: list[dict[str, str]] = []
        home = Path.home().resolve()
        for name, path in roots:
            try:
                if path.is_symlink() or not path.is_dir():
                    continue
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if resolved != home and home not in resolved.parents:
                continue
            known.append({"name": name, "target": str(resolved)})
        return known

    @staticmethod
    def recent_files(limit: int = 100) -> list[dict[str, Any]]:
        """Index file metadata from bounded known folders; never inspect content."""
        excluded = {
            ".git", ".venv", "venv", "node_modules", "__pycache__",
            "appdata", "temp", "cache", "caches", "$recycle.bin",
        }
        results: list[dict[str, Any]] = []
        inspected = 0
        max_inspected = max(500, min(5000, limit * 25))
        for folder_name in ("Downloads", "Documents", "Desktop"):
            root = Path.home() / folder_name
            if not root.is_dir():
                continue
            for current, directories, files in os.walk(root):
                directories[:] = [
                    item for item in directories if item.casefold() not in excluded
                ][:50]
                depth = len(Path(current).relative_to(root).parts)
                if depth >= 3:
                    directories[:] = []
                for filename in files:
                    path = Path(current) / filename
                    try:
                        if path.is_symlink():
                            continue
                        resolved = path.resolve(strict=True)
                        stat = resolved.stat()
                    except (OSError, RuntimeError):
                        continue
                    home = Path.home().resolve()
                    if (
                        not resolved.is_file()
                        or (resolved != home and home not in resolved.parents)
                    ):
                        continue
                    results.append({
                        "name": resolved.name,
                        "target": str(resolved),
                        "modified_at": float(stat.st_mtime),
                        "size_bytes": int(stat.st_size),
                        "folder": folder_name,
                    })
                    inspected += 1
                    if inspected >= max_inspected:
                        break
                if inspected >= max_inspected:
                    break
            if inspected >= max_inspected:
                break
        results.sort(key=lambda item: item["modified_at"], reverse=True)
        return results[:max(1, min(limit, 500))]
