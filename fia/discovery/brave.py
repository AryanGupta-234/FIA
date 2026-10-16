import httpx

from fia.config import get_settings
from fia.discovery.base import SearchResult


class BraveSearchProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        if not self.settings.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is required for live Brave discovery")
        return {
            "Accept": "application/json",
            "X-Subscription-Token": self.settings.brave_search_api_key,
        }

    async def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        params = {
            "q": f"{query} India buy online price",
            "count": min(limit, 20),
            "country": "IN",
            "search_lang": "en",
            "safesearch": "moderate",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(
                self.settings.brave_search_endpoint, params=params, headers=self._headers()
            )
            response.raise_for_status()
            payload = response.json()
        results = []
        for item in payload.get("web", {}).get("results", []):
            url, title = item.get("url"), item.get("title")
            if not url or not title:
                continue
            thumbnail = item.get("thumbnail") or {}
            image_url = thumbnail.get("src") if isinstance(thumbnail, dict) else None
            results.append(
                SearchResult(
                    title=title[:500],
                    url=url,
                    snippet=(item.get("description") or "")[:1500],
                    image_url=image_url,
                    source="brave_web",
                )
            )
        return results

    async def search_images(self, query: str, limit: int = 12) -> list[SearchResult]:
        params = {
            "q": f"{query} product India fashion",
            "count": min(limit, 20),
            "country": "IN",
            "search_lang": "en",
            "safesearch": "moderate",
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(
                self.settings.brave_images_endpoint, params=params, headers=self._headers()
            )
            response.raise_for_status()
            payload = response.json()
        images = []
        for item in payload.get("results", []):
            image = item.get("thumbnail") or {}
            image_url = image.get("src") if isinstance(image, dict) else None
            if not image_url:
                props = item.get("properties") or {}
                image_url = props.get("url")
            source_url = item.get("url") or item.get("source") or image_url
            if image_url and str(image_url).startswith(("https://", "http://")):
                images.append(
                    SearchResult(
                        title=(item.get("title") or query)[:300],
                        url=str(source_url),
                        image_url=str(image_url),
                        source="brave_images",
                    )
                )
        return images[:limit]
