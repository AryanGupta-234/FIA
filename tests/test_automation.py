from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from fia.automation import queue_due_saved_searches
from fia.db import Base
from fia.models import ResearchJob, SavedSearch


def test_scheduler_claims_only_due_active_searches_and_uses_uuid_ids(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("fia.automation.SessionLocal", factory)
    monkeypatch.setattr(
        "fia.automation.get_settings",
        lambda: type("Settings", (), {"auto_refresh_interval_minutes": 360})(),
    )
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    with factory() as db:
        due = SavedSearch(
            query="linen shirt", active=True, next_refresh_at=now - timedelta(minutes=1)
        )
        paused = SavedSearch(
            query="paused watch", active=False, next_refresh_at=now - timedelta(minutes=1)
        )
        future = SavedSearch(
            query="future watch", active=True, next_refresh_at=now + timedelta(hours=1)
        )
        db.add_all([due, paused, future])
        db.commit()
        due_id, paused_id, future_id = due.id, paused.id, future.id

    queued = queue_due_saved_searches(now)
    assert len(queued) == 1
    job_id, limit = queued[0]
    UUID(job_id)
    assert limit == 20

    with factory() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        assert job.query == "linen shirt"
        assert job.status == "queued"
        due_after = db.get(SavedSearch, due_id)
        assert due_after.last_run_at == now.replace(tzinfo=None)
        assert due_after.next_refresh_at == (now + timedelta(minutes=360)).replace(tzinfo=None)
        assert db.get(SavedSearch, paused_id).last_run_at is None
        assert db.get(SavedSearch, future_id).last_run_at is None
        assert db.scalar(select(ResearchJob.id)) == job_id

    engine.dispose()
