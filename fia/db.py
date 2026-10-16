from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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


def ensure_additive_columns(target_engine) -> None:
    """Add new fields without dropping, rewriting or replacing existing user data."""
    additions = {
        "products": {
            "original_price": "FLOAT",
            "discount_percent": "FLOAT",
            "seller_name": "VARCHAR(180)",
            "image_source": "VARCHAR(80)",
            "offer_label": "VARCHAR(180)",
            "offer_valid_until": "VARCHAR(80)",
            "product_type": "VARCHAR(120)",
            "colour": "VARCHAR(100)",
            "material": "VARCHAR(160)",
            "fit": "VARCHAR(100)",
            "size_label": "VARCHAR(80)",
            "gender": "VARCHAR(80)",
            "sku": "VARCHAR(120)",
            "gtin": "VARCHAR(32)",
            "price_checked_at": "TIMESTAMP WITH TIME ZONE",
        },
        "price_observations": {
            "original_price": "FLOAT",
            "discount_percent": "FLOAT",
            "availability": "VARCHAR(80)",
        },
        "user_preferences": {
            "price_alert_threshold_percent": "FLOAT NOT NULL DEFAULT 2.0",
        },
    }
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                    )

        if inspector.has_table("products"):
            product_columns = {
                column["name"] for column in inspect(connection).get_columns("products")
            }
            if "gtin" in product_columns:
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_products_gtin ON products (gtin)")
                )


def init_db() -> None:
    """Create new tables and apply additive migrations for existing installations."""
    Base.metadata.create_all(bind=engine)
    ensure_additive_columns(engine)
