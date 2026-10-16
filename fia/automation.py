import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from fia.config import get_settings
from fia.db import SessionLocal
from fia.models import ResearchJob, SavedSearch
from fia.research import schedule_research

logger = logging.getLogger(__name__)


def queue_due_saved_searches(now: datetime | None = None) -> list[tuple[str, int]]:
    """Claim due watches and persist UUID-backed research jobs before scheduling work."""
    settings = get_settings()
    now = now or datetime.now(UTC)
    queued: list[tuple[str, int]] = []
    with SessionLocal() as db:
        due = db.scalars(
            select(SavedSearch)
            .where(
                SavedSearch.active.is_(True),
                SavedSearch.next_refresh_at <= now,
            )
            .order_by(SavedSearch.next_refresh_at, SavedSearch.id)
            .limit(10)
            .with_for_update(skip_locked=True)
        ).all()
        for saved in due:
            job_id = str(uuid.uuid4())
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
    return queued


async def auto_refresh_loop() -> None:
    """Refresh opted-in saved searches at the configured cadence."""
    settings = get_settings()
    poll_seconds = max(15, settings.auto_refresh_poll_seconds)
    while True:
        await asyncio.sleep(poll_seconds)
        if not settings.auto_refresh_enabled or settings.search_provider == "demo":
            continue
        try:
            queued = queue_due_saved_searches()
            for job_id, limit in queued:
                schedule_research(job_id, True, limit)
        except asyncio.CancelledError:
            raise
        except Exception:
            # A transient DB/scheduling error must not permanently stop future refresh cycles.
            logger.exception("FIA saved-search scheduler iteration failed")
