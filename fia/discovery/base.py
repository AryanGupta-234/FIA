from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    image_url: str | None = None
    source: str = "web_search"


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...

    async def search_images(self, query: str, limit: int = 12) -> list[SearchResult]: ...
