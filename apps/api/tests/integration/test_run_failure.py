"""
meta:
  purpose: Integration tests (WRITTEN FIRST, fail-loud increment 2026-07-14)
           for background-run failure handling. Trace analysis found provider
           hard failures (Anthropic spend-cap 400s, Groq 429s) mid-run; an
           unhandled one previously killed the asyncio task silently and the
           run row stayed "running" forever — a zombie lane in the sidebar.
           Contract now: the run is marked failed, an "error" event is
           appended (the SSE stream's existing terminate type), and the
           exception never escapes the task.
  contract: needs docker Postgres; reuses the seeded test DB.
  deps: pytest, seeded_session fixture from test_seed_db.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from adlign.db.models import Event, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


class _AppStub:
    """Minimal stand-in for FastAPI app.state used by the run tracker."""

    def __init__(self, session_factory):
        class _State:
            pass

        self.state = _State()
        self.state.session_factory = session_factory
        self.state.live_tasks = set()


@pytest.fixture
async def app_stub(seeded_session):  # noqa: F811
    engine = create_async_engine(TEST_URL)
    app = _AppStub(async_sessionmaker(engine, expire_on_commit=False))
    yield app, seeded_session
    await engine.dispose()


async def test_crashed_run_is_marked_failed_with_error_event(app_stub):
    from adlign.api.routes.runs import _guarded

    app, session = app_stub
    run = Run(product_id="turbotax-free", mode="live", status="running",
              started_at=datetime.now(UTC))
    session.add(run)
    await session.commit()

    async def doomed():
        raise RuntimeError("provider spend cap reached")

    # must swallow the exception (a background task has no caller to raise to)
    await _guarded(app, doomed(), run_id=run.id)

    await session.refresh(run)
    assert run.status == "failed"
    assert run.finished_at is not None
    events = (await session.execute(
        select(Event).where(Event.run_id == run.id,
                            Event.event_type == "error")
    )).scalars().all()
    assert len(events) == 1
    assert "spend cap" in events[0].payload["error"]


async def test_successful_run_untouched_by_guard(app_stub):
    from adlign.api.routes.runs import _guarded

    app, session = app_stub
    run = Run(product_id="turbotax-free", mode="live", status="completed",
              started_at=datetime.now(UTC))
    session.add(run)
    await session.commit()

    async def fine():
        return None

    await _guarded(app, fine(), run_id=run.id)
    await session.refresh(run)
    assert run.status == "completed"  # guard never rewrites a healthy run
