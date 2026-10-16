import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from fia.config import get_settings
from fia.crawling.robots import RobotsPolicy


def _public_host(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, None)
        parsed = [ipaddress.ip_address(item[4][0]) for item in addresses]
        return bool(parsed) and all(address.is_global for address in parsed)
    except (OSError, ValueError):
        return False


class PageFetcher:
    def __init__(self):
        self.settings = get_settings()
        self.robots = RobotsPolicy(self.settings.crawl_user_agent)

    async def fetch(self, url: str) -> tuple[str | None, str]:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return None, "Rejected non-HTTP(S) URL"
        if not await asyncio.to_thread(_public_host, parts.hostname):
            return None, "Rejected non-public or unresolved host"
        if self.settings.crawl_respect_robots:
            allowed, reason = await self.robots.allowed(url)
            if not allowed:
                return None, "Fetch skipped: " + reason
        headers = {
            "User-Agent": self.settings.crawl_user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.crawl_timeout_seconds, follow_redirects=False
            ) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        return None, "Redirect skipped; destination must be independently validated"
                    if response.status_code != 200:
                        return None, f"HTTP {response.status_code}"
                    content_type = response.headers.get("content-type", "").lower()
                    if (
                        "text/html" not in content_type
                        and "application/xhtml+xml" not in content_type
                    ):
                        return None, "Non-HTML content skipped"
                    declared_size = response.headers.get("content-length")
                    if declared_size and int(declared_size) > self.settings.crawl_max_bytes:
                        return None, "Page exceeded configured response-size limit"
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.settings.crawl_max_bytes:
                            return None, "Page exceeded configured response-size limit"
                        chunks.append(chunk)
                    return b"".join(chunks).decode("utf-8", errors="replace"), "Fetched"
        except (httpx.HTTPError, ValueError) as exc:
            return None, f"Network error: {type(exc).__name__}"
