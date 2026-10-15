from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from fia.config import get_settings


class Base(DeclarativeBase):
    pass


def build_engine():
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        path = settings.database_path
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(settings.database_url, connect_args={"check_same_thread": False})
    return create_engine(settings.database_url, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
