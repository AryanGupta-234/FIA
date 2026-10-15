from fia.discovery.base import SearchResult


class DemoSearchProvider:
    """Deterministic fixture provider; these are not real listings or live offers."""

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        items = [
            SearchResult(f"Demo: Minimal white sneakers — {query}",
                         "https://www.myntra.com/demo-minimal-white-sneakers",
                         "DEMO DATA — illustrative listing, not a current product or price."),
            SearchResult(f"Demo: Everyday casual shoes — {query}",
                         "https://www.ajio.com/demo-everyday-casual-shoes",
                         "DEMO DATA — illustrative listing, not a current product or price."),
            SearchResult(f"Demo: Canvas low-top footwear — {query}",
                         "https://www.amazon.in/demo-canvas-low-top",
                         "DEMO DATA — illustrative listing, not a current product or price."),
        ]
        return items[:limit]
