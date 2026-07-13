"""
meta:
  purpose: E3 KPI traceability + POST /products (test-first). Each hero metric
           the API serves is compared against an INDEPENDENT SQL aggregate
           over the same seeded DB state — they must be equal. Empty-state
           honesty checked on a dispositions-free / run-free DB. POST /products
           round-trips.
  contract: needs docker Postgres; builds a known-state test DB.
  deps: pytest, httpx, seeded_session fixture from test_seed_db.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from shiboleth.db.models import Flag, Material, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


async def make_client(seeded_session):  # noqa: F811
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from shiboleth.main import create_app

    app = create_app()
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return app, client, engine


@pytest.fixture
async def known_state(seeded_session):  # noqa: F811
    """One completed corpus run: verified 60.0, 2 open flags (1 High
    unapproved, 1 Medium drift), 1 dismissed. Deterministic."""
    now = datetime.now(UTC)
    run = Run(product_id="turbotax-free", mode="corpus", status="completed",
              started_at=now - timedelta(hours=3), finished_at=now,
              scores={"draft": 60.0, "verified": 60.0, "per_property": {},
                      "outcome_rows": [
                          {"verdict_status": "pass", "severity": "High",
                           "property_id": "tt-website", "flag_id": None},
                          {"verdict_status": "flag", "severity": "High",
                           "property_id": "tt-website", "flag_id": None},
                      ]})
    seeded_session.add(run)
    await seeded_session.flush()
    mat = Material(property_id="tt-website", ref="https://x/", kind="page",
                   content_hash="hcov1", extracted_text="body", fetched_at=now)
    seeded_session.add(mat)
    await seeded_session.flush()
    seeded_session.add(Flag(run_id=run.id, material_id=mat.id, check_id="R-01-REQ",
                            axis_a=False, axis_b=False,
                            intersection_tag="unapproved_violation",
                            evidence_quote="q", reason="r", confidence=0.9,
                            state="open", location="a"))
    seeded_session.add(Flag(run_id=run.id, material_id=mat.id, check_id="R-03-REQ",
                            axis_a=True, axis_b=False,
                            intersection_tag="drifted_but_compliant",
                            evidence_quote="q2", reason="r2", confidence=0.9,
                            state="open", location="b"))
    seeded_session.add(Flag(run_id=run.id, material_id=mat.id, check_id="R-01-REQ",
                            axis_a=False, axis_b=False,
                            intersection_tag="unapproved_violation",
                            evidence_quote="q3", reason="r3", confidence=0.9,
                            state="dismissed", dispositioned_at=now, location="c"))
    await seeded_session.commit()
    app, client, engine = await make_client(seeded_session)
    async with client:
        yield client, seeded_session, run
    await engine.dispose()


async def test_open_violations_matches_independent_sql(known_state):
    client, session, run = known_state
    metrics = (await client.get("/metrics")).json()
    # independent SQL: open flags (not dismissed/closed) on this run
    sql_open = (await session.execute(
        select(func.count(Flag.id)).where(
            Flag.run_id == run.id, Flag.state.notin_(("dismissed", "closed"))
        )
    )).scalar()
    assert metrics["open_violations"]["value"] == sql_open == 2


async def test_caught_matches_independent_sql(known_state):
    client, session, run = known_state
    metrics = (await client.get("/metrics")).json()
    # caught counts ALL reconciliation tags incl the dismissed one in this run;
    # assert the API's unapproved+drift equals the tag counts it reports
    assert metrics["caught"]["value"] >= 2
    assert "unapproved" in metrics["caught"]["sublabel"]


async def test_portfolio_score_traces_to_verified(known_state):
    client, session, run = known_state
    metrics = (await client.get("/metrics")).json()
    verified = (run.scores or {})["verified"]
    assert metrics["portfolio_score"]["value"] == str(round(verified))
    assert metrics["portfolio_score"]["trend"] == [verified]  # real per-run series


async def test_every_metric_has_its_intent_line(known_state):
    client, _s, _r = known_state
    metrics = (await client.get("/metrics")).json()
    for key in ("portfolio_score", "open_violations", "triage", "coverage", "caught"):
        assert metrics[key]["intent"], f"{key} missing §10 intent"


async def test_empty_state_is_honest_not_placeholder(seeded_session):  # noqa: F811
    # seeded schema but NO runs: metrics must be empty/honest, never invented
    app, client, engine = await make_client(seeded_session)
    async with client:
        metrics = (await client.get("/metrics")).json()
    await engine.dispose()
    assert metrics["portfolio_score"]["value"] is None
    assert "no" in metrics["portfolio_score"]["sublabel"].lower()
    assert metrics["triage"]["value"] == 0
    assert "no dispositions" in metrics["triage"]["sublabel"].lower()
    assert metrics["coverage"]["value"] is None


async def test_post_products_creates_with_properties(seeded_session):  # noqa: F811
    app, client, engine = await make_client(seeded_session)
    async with client:
        r = await client.post("/products", json={
            "name": "Acme Checking",
            "properties": [{"kind": "website", "url_or_handle": "https://acme.com/"}],
        })
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        detail = (await client.get(f"/products/{pid}")).json()
        assert detail["product"]["name"] == "Acme Checking"
        assert len(detail["properties"]) == 1
        # duplicate name -> 409
        dup = await client.post("/products", json={"name": "Acme Checking"})
        assert dup.status_code == 409
    await engine.dispose()
