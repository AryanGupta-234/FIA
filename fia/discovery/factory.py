from fia.config import get_settings
from fia.discovery.brave import BraveSearchProvider
from fia.discovery.demo import DemoSearchProvider


def get_search_provider():
    choice = get_settings().search_provider.lower()
    if choice == "brave":
        return BraveSearchProvider()
    if choice == "demo":
        return DemoSearchProvider()
    raise ValueError(f"Unsupported SEARCH_PROVIDER: {choice}")
