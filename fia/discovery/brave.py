import httpx

from fia.config import get_settings
from fia.discovery.base import SearchResult


class BraveSearchProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if not self.settings.brave_search_api_key:
            raise RuntimeError("SEARCH_PROVIDER=brave requires BRAVE_SEARCH_API_KEY")
        params = {"q": query, "count": min(limit, 20), "country": "IN", "search_lang": "en"}
        headers = {"Accept": "application/json",
                   "X-Subscription-Token": self.settings.brave_search_api_key}
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            response = await client.get(self.settings.brave_search_endpoint,
                                        params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        results = []
        for item in payload.get("web", {}).get("results", []):
            if item.get("url") and item.get("title"):
                results.append(SearchResult(item["title"][:500], item["url"],
                                            (item.get("description") or "")[:1500]))
        return results
