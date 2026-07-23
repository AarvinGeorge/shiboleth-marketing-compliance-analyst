"""
meta:
  purpose: Integration tests for the M4 events surface: the JSON events list
           (U7 why-flagged chain source) and the SSE stream contract
           (persisted rows replayed in ts order, envelope fields present,
           stream closes after run_finished).
  contract: GET /runs/{id}/events.json ordered; GET /runs/{id}/events (SSE)
            yields every persisted event then terminates on run_finished.
  deps: docker Postgres (skipped when down); seeded test DB fixtures.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from adlign.db.models import Event, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


@pytest.fixture
async def client_with_run(seeded_session):  # noqa: F811
    run = Run(product_id="turbotax-free", mode="corpus", status="completed")
    seeded_session.add(run)
    await seeded_session.flush()
    for i, etype in enumerate(
        ["run_started", "node_started", "check_result", "run_finished"]
    ):
        seeded_session.add(Event(run_id=run.id, node="graph", event_type=etype,
                                 payload={"seq": i}))
        await seeded_session.flush()
    await seeded_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from adlign.main import create_app

    app = create_app()
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, run
    await engine.dispose()


async def test_events_json_ordered(client_with_run):
    client, run = client_with_run
    r = await client.get(f"/runs/{run.id}/events.json")
    assert r.status_code == 200
    events = r.json()
    assert [e["type"] for e in events] == [
        "run_started", "node_started", "check_result", "run_finished"
    ]
    assert all("payload" in e and "ts" in e for e in events)


async def test_sse_replays_and_terminates(client_with_run):
    client, run = client_with_run
    types = []
    async with client.stream("GET", f"/runs/{run.id}/events") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                types.append(line.split(":", 1)[1].strip())
    # stream ENDED on its own (run_finished terminates it) with all events
    assert types == ["run_started", "node_started", "check_result", "run_finished"]
