from sqlalchemy import create_engine, inspect, text

from fia.db import ensure_additive_columns


def test_additive_migration_preserves_legacy_tables_and_adds_new_fields():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE price_observations (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE user_preferences (id INTEGER PRIMARY KEY)"))

    ensure_additive_columns(engine)

    inspector = inspect(engine)
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    preference_columns = {
        column["name"] for column in inspector.get_columns("user_preferences")
    }
    assert {"id", "price_checked_at", "colour", "material", "gtin"} <= product_columns
    assert {"id", "price_alert_threshold_percent"} <= preference_columns
    assert "ix_products_gtin" in {index["name"] for index in inspector.get_indexes("products")}
    engine.dispose()
