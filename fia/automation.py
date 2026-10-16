import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from fia.config import get_settings
from fia.db import SessionLocal
from fia.models import ResearchJob, SavedSearch
from fia.research import schedule_research


async def auto_refresh_loop() -> None:
    """Refresh opted-in saved searches at the configured cadence."""
    settings = get_settings()
    poll_seconds = max(15, settings.auto_refresh_poll_seconds)
    while True:
        await asyncio.sleep(poll_seconds)
        if not settings.auto_refresh_enabled or settings.search_provider == "demo":
            continue
        now = datetime.now(UTC)
        queued: list[tuple[str, int]] = []
        with SessionLocal() as db:
            due = db.scalars(
                select(SavedSearch).where(
                    SavedSearch.active.is_(True),
                    SavedSearch.next_refresh_at <= now,
                ).limit(10)
            ).all()
            for saved in due:
                job_id = f"auto-{saved.id}-{int(now.timestamp())}"
                db.add(
                    ResearchJob(
                        id=job_id,
                        query=saved.query,
                        budget_max=saved.budget_max,
                        category=saved.category,
                        status="queued",
                    )
                )
                saved.last_run_at = now
                saved.next_refresh_at = now + timedelta(
                    minutes=max(60, settings.auto_refresh_interval_minutes)
                )
                queued.append((job_id, 20))
            db.commit()
        for job_id, limit in queued:
            schedule_research(job_id, True, limit)
