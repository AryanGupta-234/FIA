from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx


class RobotsPolicy:
    def __init__(self, user_agent: str, timeout: float = 5.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self.cache: dict[str, RobotFileParser | None] = {}

    async def allowed(self, url: str) -> tuple[bool, str]:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return False, "Invalid URL"
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.cache:
            parser = RobotFileParser()
            parser.set_url(origin + "/robots.txt")
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, follow_redirects=False
                ) as client:
                    response = await client.get(
                        origin + "/robots.txt", headers={"User-Agent": self.user_agent}
                    )
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                    self.cache[origin] = parser
                elif response.status_code in (404, 410):
                    parser.parse([])
                    self.cache[origin] = parser
                else:
                    self.cache[origin] = None
            except httpx.HTTPError:
                self.cache[origin] = None
        parser = self.cache[origin]
        if parser is None:
            return False, "Robots policy denied or unavailable; fail-closed"
        return parser.can_fetch(self.user_agent, url), "robots.txt policy"
