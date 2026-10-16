from fia.discovery.base import SearchResult


class DemoSearchProvider:
    """Deterministic local fixtures. Results are labelled demo, never live offers."""

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        fixtures = [
            SearchResult(
                title=f"Demo discovery: Contemporary everyday essentials — {query}",
                url="https://www.myntra.com/demo-everyday-essentials",
                snippet=(
                    "DEMO DATA — illustrative search result; "
                    "not a live product listing or price."
                ),
                source="demo",
            ),
            SearchResult(
                title=f"Demo discovery: Minimal wardrobe edit — {query}",
                url="https://www.ajio.com/demo-minimal-wardrobe",
                snippet="DEMO DATA — illustrative search result; not a live product listing or price.",
                source="demo",
            ),
            SearchResult(
                title=f"Demo discovery: Modern casual collection — {query}",
                url="https://www.amazon.in/demo-modern-casual",
                snippet="DEMO DATA — illustrative search result; not a live product listing or price.",
                source="demo",
            ),
        ]
        return fixtures[:limit]

    async def search_images(self, query: str, limit: int = 12) -> list[SearchResult]:
        return []
