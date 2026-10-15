from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]: ...
