from datetime import UTC, datetime, timedelta

from fia.services.freshness import price_freshness


def test_missing_price_timestamp_is_unknown_not_fresh():
    assert price_freshness(None, 72)["status"] == "unknown"
    assert price_freshness(None, 72)["is_stale"] is True


def test_price_timestamp_is_fresh_inside_window():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    checked = now - timedelta(hours=36)
    result = price_freshness(checked, 72, now)
    assert result == {"status": "fresh", "age_hours": 36.0, "is_stale": False}


def test_naive_sqlite_timestamp_is_interpreted_as_utc_and_expires():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    checked = (now - timedelta(hours=73)).replace(tzinfo=None)
    result = price_freshness(checked, 72, now)
    assert result["status"] == "stale"
    assert result["is_stale"] is True
