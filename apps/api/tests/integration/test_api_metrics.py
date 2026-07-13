"""
meta:
  purpose: E3 KPI traceability + POST /products (test-first). Every number
           GET /metrics serves (metrics overhaul 2026-07-13: open-flags donut
           by tag + open-violations tile) is compared against an INDEPENDENT
           SQL aggregate over the same seeded DB state — they must be equal.
           Includes the latest-run-only rule (older runs never double count)
           and the needs_review partition (its own donut slice, NOT a
           violation). Empty-state honesty checked on a run-free DB.
           POST /products round-trips.
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


def _flag(run_id: str, material_id: str, check_id: str, tag: str,
          state: str = "open", axis_a: bool = False) -> Flag:
    return Flag(run_id=run_id, material_id=material_id, check_id=check_id,
                axis_a=axis_a, axis_b=False, intersection_tag=tag,
                evidence_quote="q", reason="r", confidence=0.9,
                state=state, location="loc")


@pytest.fixture
async def known_state(seeded_session):  # noqa: F811
    """LATEST run: 4 flags — 3 open (1 UV High, 1 drift Medium, 1 open
    needs_review via outcome_rows) + 1 dismissed UV. Plus an OLDER run with
    2 open flags that must never be counted (latest-run-only rule).
    Expected metrics: total 3; by_tag UV 1 / drift 1 / needs_review 1 /
    other 0; violations 2 (total minus needs_review); violations_high 1."""
    now = datetime.now(UTC)
    mat = Material(property_id="tt-website", ref="https://x/", kind="page",
                   content_hash="hmet1", extracted_text="body", fetched_at=now)
    seeded_session.add(mat)
    await seeded_session.flush()

    old = Run(product_id="turbotax-free", mode="corpus", status="completed",
              started_at=now - timedelta(days=2),
              finished_at=now - timedelta(days=2), scores={})
    seeded_session.add(old)
    await seeded_session.flush()
    seeded_session.add(_flag(old.id, mat.id, "R-01-REQ", "unapproved_violation"))
    seeded_session.add(_flag(old.id, mat.id, "R-02-REQ", "unapproved_violation"))

    run = Run(product_id="turbotax-free", mode="corpus", status="completed",
              started_at=now - timedelta(hours=3), finished_at=now)
    seeded_session.add(run)
    await seeded_session.flush()
    f_uv = _flag(run.id, mat.id, "R-01-REQ", "unapproved_violation")
    f_drift = _flag(run.id, mat.id, "R-03-REQ", "drifted_but_compliant",
                    axis_a=True)
    f_review = _flag(run.id, mat.id, "R-02-REQ", "all_good", axis_a=True)
    f_dismissed = _flag(run.id, mat.id, "R-01-REQ", "unapproved_violation",
                        state="dismissed")
    f_dismissed.dispositioned_at = now
    seeded_session.add_all([f_uv, f_drift, f_review, f_dismissed])
    await seeded_session.flush()
    run.scores = {
        "draft": 60.0, "verified": 60.0, "per_property": {},
        "needs_review_count": 1,
        "outcome_rows": [
            {"verdict_status": "flag", "severity": "High",
             "property_id": "tt-website", "flag_id": f_uv.id},
            {"verdict_status": "flag", "severity": "Medium",
             "property_id": "tt-website", "flag_id": f_drift.id},
            {"verdict_status": "needs_review", "severity": "High",
             "property_id": "tt-website", "flag_id": f_review.id},
            {"verdict_status": "flag", "severity": "High",
             "property_id": "tt-website", "flag_id": f_dismissed.id},
        ],
    }
    await seeded_session.commit()
    app, client, engine = await make_client(seeded_session)
    async with client:
        yield client, seeded_session, run, {
            "review_flag": f_review, "old_run": old,
        }
    await engine.dispose()


async def test_open_flags_total_matches_independent_sql(known_state):
    client, session, run, _ids = known_state
    metrics = (await client.get("/metrics")).json()
    # independent SQL: open flags on the LATEST run only
    sql_open = (await session.execute(
        select(func.count(Flag.id)).where(
            Flag.run_id == run.id, Flag.state == "open"
        )
    )).scalar()
    assert metrics["open_flags_total"] == sql_open == 3
    # the donut buckets partition the total exactly
    assert sum(metrics["open_flags_by_tag"].values()) == metrics["open_flags_total"]


async def test_open_flags_by_tag_partitions_with_needs_review(known_state):
    client, _session, run, ids = known_state
    metrics = (await client.get("/metrics")).json()
    assert metrics["open_flags_by_tag"] == {
        "unapproved_violation": 1, "drifted_but_compliant": 1,
        "needs_review": 1, "other": 0,
    }
    # the needs_review bucket traces to the persisted outcome rows
    review_ids = {row["flag_id"] for row in run.scores["outcome_rows"]
                  if row["verdict_status"] == "needs_review"}
    assert ids["review_flag"].id in review_ids


async def test_open_violations_excludes_needs_review(known_state):
    client, _session, _run, _ids = known_state
    metrics = (await client.get("/metrics")).json()
    # tile definition: open flags with a violation verdict = total - review
    assert metrics["open_violations"] == (
        metrics["open_flags_total"]
        - metrics["open_flags_by_tag"]["needs_review"]
    ) == 2
    # severity: only the open UV flag is High (drift is R-03 = Medium)
    assert metrics["open_violations_high"] == 1


async def test_latest_run_only_never_double_counts(known_state):
    client, session, _run, ids = known_state
    # the older run has 2 open flags; metrics must ignore them entirely
    sql_old_open = (await session.execute(
        select(func.count(Flag.id)).where(
            Flag.run_id == ids["old_run"].id, Flag.state == "open"
        )
    )).scalar()
    assert sql_old_open == 2
    metrics = (await client.get("/metrics")).json()
    assert metrics["open_flags_total"] == 3  # not 5


async def test_product_flags_carry_verdict_status(known_state):
    client, _session, _run, ids = known_state
    # ONE violation definition everywhere: the product payload marks
    # needs_review flags so U6 excludes them exactly like /metrics does.
    detail = (await client.get("/products/turbotax-free")).json()
    statuses = {f["id"]: f["verdict_status"] for f in detail["flags"]}
    assert statuses[ids["review_flag"].id] == "needs_review"
    assert sorted(set(statuses.values())) == ["flag", "needs_review"]
    open_violations_product = sum(
        1 for f in detail["flags"]
        if f["state"] == "open" and f["verdict_status"] == "flag"
    )
    metrics = (await client.get("/metrics")).json()
    assert open_violations_product == metrics["open_violations"]


async def test_empty_state_is_honest_not_placeholder(seeded_session):  # noqa: F811
    # seeded schema but NO runs: metrics must be zeros, never invented
    app, client, engine = await make_client(seeded_session)
    async with client:
        metrics = (await client.get("/metrics")).json()
    await engine.dispose()
    assert metrics["open_flags_total"] == 0
    assert metrics["open_violations"] == 0
    assert metrics["open_violations_high"] == 0
    assert sum(metrics["open_flags_by_tag"].values()) == 0


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
