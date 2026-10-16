from datetime import UTC, datetime


def price_freshness(checked_at: datetime | None, stale_after_hours: int, now=None) -> dict:
    """Describe whether a stored price has a recent source observation."""
    if checked_at is None:
        return {"status": "unknown", "age_hours": None, "is_stale": True}
    now = now or datetime.now(UTC)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    age_hours = max(0.0, (now - checked_at).total_seconds() / 3600)
    stale = age_hours > max(1, stale_after_hours)
    return {
        "status": "stale" if stale else "fresh",
        "age_hours": round(age_hours, 1),
        "is_stale": stale,
    }
