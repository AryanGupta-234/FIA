from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fashion Intelligence Agent"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "sqlite:///./data/fia.db"
    cors_origins: str = "http://localhost:5173"
    search_provider: str = "demo"
    brave_search_api_key: str = ""
    brave_search_endpoint: str = "https://api.search.brave.com/res/v1/web/search"
    brave_images_endpoint: str = "https://api.search.brave.com/res/v1/images/search"
    search_result_count: int = 20
    crawl_user_agent: str = "FIAResearchBot/0.2 (+https://github.com/AryanGupta-234/FIA)"
    crawl_timeout_seconds: float = 8.0
    crawl_max_bytes: int = 1_500_000
    crawl_max_pages_per_job: int = 8
    crawl_respect_robots: bool = True
    auto_refresh_enabled: bool = True
    auto_refresh_interval_minutes: int = 360
    auto_refresh_poll_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def database_path(self) -> Path | None:
        if self.database_url.startswith("sqlite:///") and self.database_url != "sqlite:///:memory:":
            return Path(self.database_url[len("sqlite:///"):]).resolve()
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
