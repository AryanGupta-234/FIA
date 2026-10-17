from __future__ import annotations

import asyncio
import threading
import time
from typing import Any


class WindowsMediaSessionAdapter:
    """Tier-2 Windows media-session adapter; never reads track metadata."""

    @staticmethod
    async def _session(application: str | None):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        )
        manager = await SessionManager.request_async()
        if application:
            wanted = application.casefold().strip()
            for session in manager.get_sessions():
                app_id = str(session.source_app_user_model_id or "")
                if wanted in app_id.casefold():
                    return session
            raise LookupError("Requested application has no active media session.")
        session = manager.get_current_session()
        if session is None:
            raise LookupError("No active Windows media session.")
        return session

    @staticmethod
    def _status(session) -> str:
        info = session.get_playback_info()
        value = getattr(info, "playback_status", None)
        return str(value).split(".")[-1].casefold() if value is not None else "unknown"

    @staticmethod
    def _run(factory, timeout_seconds: float = 8.0):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(factory())
        completed = threading.Event()
        result: dict[str, Any] = {}
        errors: list[BaseException] = []

        def worker():
            try:
                result["value"] = asyncio.run(factory())
            except BaseException as exc:
                errors.append(exc)
            finally:
                completed.set()

        threading.Thread(target=worker, name="PrixonMediaWinRT", daemon=True).start()
        if not completed.wait(timeout_seconds):
            raise TimeoutError("Media API call timed out.")
        if errors:
            raise errors[0]
        return result.get("value")

    def snapshot(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}

        async def read():
            session = await self._session(args.get("application"))
            info = session.get_playback_info()
            return {
                "session_available": True,
                "session_app_id": str(session.source_app_user_model_id or ""),
                "playback_status": self._status(session),
                "can_play": bool(getattr(info.controls, "is_play_enabled", False)),
                "can_pause": bool(getattr(info.controls, "is_pause_enabled", False)),
                "can_skip_next": bool(getattr(info.controls, "is_next_enabled", False)),
                "can_skip_previous": bool(getattr(info.controls, "is_previous_enabled", False)),
            }

        return self._run(read)

    def execute(self, action: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        methods = {
            "media.play": "play",
            "media.pause": "pause",
            "media.stop": "stop",
            "media.skip_next": "next",
            "media.skip_previous": "previous",
        }
        if action == "media.status":
            return self.snapshot(args)
        command = methods.get(action)
        if command is None:
            raise ValueError(f"Unsupported media action: {action}")

        async def control():
            session = await self._session(args.get("application"))
            calls = {
                "play": session.try_play_async,
                "pause": session.try_pause_async,
                "stop": session.try_stop_async,
                "next": session.try_skip_next_async,
                "previous": session.try_skip_previous_async,
            }
            accepted = bool(await calls[command]())
            if not accepted:
                raise RuntimeError(f"Media session rejected {command}.")
            wanted = {"play": "playing", "pause": "paused", "stop": "stopped"}.get(command)
            deadline = time.monotonic() + 1.5
            status = self._status(session)
            while wanted and status != wanted and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                status = self._status(session)
            return {
                "accepted": True,
                "session_available": True,
                "session_app_id": str(session.source_app_user_model_id or ""),
                "playback_status": status,
                "command": command,
            }

        return self._run(control)

    def undo(self, action: str, args: dict[str, Any], before: dict[str, Any]) -> bool:
        old_status = str(before.get("playback_status") or "unknown").casefold()
        compensation = {
            "media.skip_next": "media.skip_previous",
            "media.skip_previous": "media.skip_next",
        }.get(action)
        if action in {"media.play", "media.pause", "media.stop"}:
            compensation = "media.play" if old_status == "playing" else "media.pause"
        if not compensation:
            return False
        try:
            return bool(self.execute(compensation, args).get("accepted"))
        except Exception:
            return False


class WindowsOfficeAdapter:
    """Tier-2 Office COM adapter exposing counts and save-state only."""

    APPLICATIONS = (
        ("Word", "Word.Application", "Documents"),
        ("Excel", "Excel.Application", "Workbooks"),
        ("PowerPoint", "PowerPoint.Application", "Presentations"),
    )

    def status(self) -> dict[str, Any]:
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError(
                "Office automation requires the optional pywin32 Windows dependency."
            ) from exc

        rows: list[dict[str, Any]] = []
        pythoncom.CoInitialize()
        try:
            for display_name, prog_id, collection_name in self.APPLICATIONS:
                try:
                    application = win32com.client.GetActiveObject(prog_id)
                except Exception:
                    continue
                collection = getattr(application, collection_name, None)
                try:
                    count = int(collection.Count) if collection is not None else 0
                except Exception:
                    count = 0
                unsaved = 0
                if collection is not None:
                    for index in range(1, min(count, 100) + 1):
                        try:
                            document = collection.Item(index)
                            if not bool(document.Saved):
                                unsaved += 1
                        except Exception:
                            continue
                rows.append({
                    "application": display_name,
                    "open_count": count,
                    "unsaved_count": unsaved,
                })
        finally:
            pythoncom.CoUninitialize()

        return {
            "automation_available": True,
            "applications": rows,
            "open_document_count": sum(item["open_count"] for item in rows),
            "unsaved_document_count": sum(item["unsaved_count"] for item in rows),
            "content_read": False,
            "names_or_paths_read": False,
        }

    def execute(self, action: str, _args: dict[str, Any] | None = None) -> dict[str, Any]:
        if action != "office.status":
            raise ValueError(f"Office action is not registered: {action}")
        return self.status()


class ChromiumDebugAdapter:
    """Loopback-only Chromium diagnostics; never reads URLs, titles or page contents."""

    def __init__(self, *, enabled: bool = False, port: int = 9222) -> None:
        self.enabled = bool(enabled)
        self.port = max(1024, min(int(port), 65535))

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            raise PermissionError("Browser debugging adapter is disabled by configuration.")

        import json
        import urllib.request
        from urllib.parse import urlsplit

        version_url = f"http://127.0.0.1:{self.port}/json/version"
        request = urllib.request.Request(
            version_url,
            headers={"Accept": "application/json", "User-Agent": "PrixonLocalDiagnostics/1.0"},
        )
        with urllib.request.urlopen(request, timeout=2.0) as response:
            if response.status != 200:
                raise ConnectionError("Local browser debug endpoint returned a non-200 response.")
            version = json.loads(response.read(64 * 1024).decode("utf-8"))

        websocket_url = str(version.get("webSocketDebuggerUrl") or "")
        parsed = urlsplit(websocket_url)
        if (
            parsed.scheme != "ws"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.port != self.port
            or parsed.username is not None
            or parsed.password is not None
            or not parsed.path.startswith("/devtools/browser/")
        ):
            raise PermissionError("Browser debugging websocket did not resolve to the configured loopback port.")

        try:
            from websockets.sync.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "Browser debugging requires the optional .[browser] websocket dependency."
            ) from exc

        with connect(
            websocket_url,
            open_timeout=2.0,
            close_timeout=1.0,
            max_size=64 * 1024,
            compression=None,
        ) as socket:
            def command(command_id: int, method: str) -> dict[str, Any]:
                socket.send(json.dumps({"id": command_id, "method": method}))
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    message = json.loads(socket.recv(timeout=max(0.1, deadline - time.monotonic())))
                    if message.get("id") == command_id:
                        if message.get("error"):
                            raise RuntimeError(f"Chromium debugging command failed: {method}")
                        return message.get("result") or {}
                raise TimeoutError(f"Chromium debugging command timed out: {method}")

            browser_info = command(1, "Browser.getVersion")
            targets = command(2, "Target.getTargets").get("targetInfos", [])
            target_counts: dict[str, int] = {}
            for item in targets:
                kind = str(item.get("type") or "other")[:32]
                target_counts[kind] = target_counts.get(kind, 0) + 1

        return {
            "enabled": True,
            "reachable": True,
            "port": self.port,
            "browser_product": str(browser_info.get("product") or "Chromium")[:100],
            "protocol_version": str(browser_info.get("protocolVersion") or "")[:40],
            "target_count": sum(target_counts.values()),
            "target_type_counts": target_counts,
            "metadata_only": True,
            "urls_read": False,
            "titles_read": False,
            "page_content_read": False,
        }

    def execute(self, action: str, _args: dict[str, Any] | None = None) -> dict[str, Any]:
        if action != "browser.debug_status":
            raise ValueError(f"Browser action is not registered: {action}")
        return self.status()
