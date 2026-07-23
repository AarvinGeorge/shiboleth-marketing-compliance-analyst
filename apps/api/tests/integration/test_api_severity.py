"""
meta:
  purpose: Integration tests (WRITTEN FIRST, per-flag severity increment
           2026-07-14) for the human-editable severity override: PATCH
           /flags/{id}/severity round-trip incl. reset-to-null, audit event
           rows ({from, to}), the effective-severity rule (override ??
           rule severity) in the products payload, and the /metrics
           severity partition shifting by exactly one when a High flag is
           overridden to Low. Persisted outcome_rows are NEVER rewritten:
           overrides affect display and metrics only.
  contract: needs docker Postgres; builds a known-state test DB.
  deps: pytest, httpx, seeded_session fixture from test_seed_db.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from adlign.db.models import Event, Flag, Material, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


@pytest.fixture
async def client_with_flags(seeded_session):  # noqa: F811
    """Latest run with 2 open flags: R-01-REQ (rule severity High, UV) and
    R-03-REQ (rule severity Medium, drift). Matrix-aware recommendation
    (2026-07-14): drift recommends Low, so the baseline partition is
    {High: 1, Medium: 0, Low: 1}."""
    now = datetime.now(UTC)
    mat = Material(property_id="tt-website", ref="https://x/", kind="page",
                   content_hash="hsev1", extracted_text="body", fetched_at=now)
    seeded_session.add(mat)
    await seeded_session.flush()
    run = Run(product_id="turbotax-free", mode="corpus", status="completed",
              started_at=now - timedelta(hours=1), finished_at=now,
              scores={"draft": 50.0, "verified": 50.0, "outcome_rows": []})
    seeded_session.add(run)
    await seeded_session.flush()
    f_high = Flag(run_id=run.id, material_id=mat.id, check_id="R-01-REQ",
                  axis_a=False, axis_b=False,
                  intersection_tag="unapproved_violation",
                  evidence_quote="q", reason="r", confidence=0.9,
                  state="open", location="a")
    f_med = Flag(run_id=run.id, material_id=mat.id, check_id="R-03-REQ",
                 axis_a=True, axis_b=False,
                 intersection_tag="drifted_but_compliant",
                 evidence_quote="q2", reason="r2", confidence=0.9,
                 state="open", location="b")
    seeded_session.add_all([f_high, f_med])
    await seeded_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from adlign.main import create_app

    app = create_app()
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as client:
        yield client, seeded_session, f_high, f_med
    await engine.dispose()


def _payload_flag(body: dict, flag_id: str) -> dict:
    return next(f for f in body["flags"] if f["id"] == flag_id)


async def test_override_roundtrip_and_reset(client_with_flags):
    client, session, f_high, _f_med = client_with_flags

    # baseline: effective == recommended (rule severity), no override
    detail = (await client.get("/products/turbotax-free")).json()
    row = _payload_flag(detail, f_high.id)
    assert row["severity_recommended"] == "High"
    assert row["severity_effective"] == "High"
    assert row["severity_overridden"] is False

    # override High -> Low
    r = await client.patch(f"/flags/{f_high.id}/severity",
                           json={"severity": "Low"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["severity_effective"] == "Low"
    assert body["severity_recommended"] == "High"
    assert body["severity_overridden"] is True

    detail = (await client.get("/products/turbotax-free")).json()
    row = _payload_flag(detail, f_high.id)
    assert row["severity_effective"] == "Low"
    assert row["severity_recommended"] == "High"
    assert row["severity_overridden"] is True

    # reset to recommended (null)
    r = await client.patch(f"/flags/{f_high.id}/severity",
                           json={"severity": None})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["severity_effective"] == "High"
    assert body["severity_overridden"] is False

    detail = (await client.get("/products/turbotax-free")).json()
    row = _payload_flag(detail, f_high.id)
    assert row["severity_effective"] == "High"
    assert row["severity_overridden"] is False

    # audit: one event per change, {from, to} effective values
    events = (await session.execute(
        select(Event).where(Event.flag_id == f_high.id,
                            Event.event_type == "severity_overridden")
        .order_by(Event.ts)
    )).scalars().all()
    assert [e.payload for e in events] == [
        {"from": "High", "to": "Low"},
        {"from": "Low", "to": "High"},
    ]


async def test_override_guards(client_with_flags):
    client, _session, f_high, _f_med = client_with_flags
    r = await client.patch("/flags/does-not-exist/severity",
                           json={"severity": "Low"})
    assert r.status_code == 404
    r = await client.patch(f"/flags/{f_high.id}/severity",
                           json={"severity": "Critical"})
    assert r.status_code == 422


async def test_metrics_partition_respects_override(client_with_flags):
    client, _session, f_high, _f_med = client_with_flags
    metrics = (await client.get("/metrics")).json()
    assert metrics["open_violations_by_severity"] == {
        "High": 1, "Medium": 0, "Low": 1,
    }

    # flip the High flag to Low: the partition shifts by exactly one and
    # the violations total is untouched
    r = await client.patch(f"/flags/{f_high.id}/severity",
                           json={"severity": "Low"})
    assert r.status_code == 200, r.text
    metrics = (await client.get("/metrics")).json()
    assert metrics["open_violations_by_severity"] == {
        "High": 0, "Medium": 0, "Low": 2,
    }
    assert metrics["open_violations"] == 2
    assert metrics["open_violations_high"] == 0

    # reset restores the baseline
    await client.patch(f"/flags/{f_high.id}/severity", json={"severity": None})
    metrics = (await client.get("/metrics")).json()
    assert metrics["open_violations_by_severity"] == {
        "High": 1, "Medium": 0, "Low": 1,
    }


async def test_matrix_aware_recommendation_and_reset(client_with_flags):
    """Drift on a Medium rule recommends Low (matrix-aware, 2026-07-14);
    override and null-reset land back on the MATRIX value, not the rule's."""
    client, _session, _f_high, f_med = client_with_flags
    detail = (await client.get("/products/turbotax-free")).json()
    row = _payload_flag(detail, f_med.id)
    assert row["severity_recommended"] == "Low"
    assert row["severity_effective"] == "Low"

    r = await client.patch(f"/flags/{f_med.id}/severity",
                           json={"severity": "High"})
    assert r.status_code == 200, r.text
    assert r.json()["severity_effective"] == "High"
    assert r.json()["severity_recommended"] == "Low"

    r = await client.patch(f"/flags/{f_med.id}/severity",
                           json={"severity": None})
    assert r.json()["severity_effective"] == "Low"


async def test_flag_payload_discloses_measured_accuracy_not_confidence(
        client_with_flags):
    """The self-reported LLM confidence is uncalibrated (trace analysis
    2026-07-14: flags cluster at 0.95 while measured accuracy is 65-81%);
    the payload now carries the GT v2 measured accuracy instead."""
    client, _session, f_high, _f_med = client_with_flags
    detail = (await client.get("/products/turbotax-free")).json()
    row = _payload_flag(detail, f_high.id)
    assert "confidence" not in row["verdicts"]
    acc = row["verdicts"]["accuracy_measured"]
    assert acc is not None
    assert 0.0 < acc["accuracy"] <= 1.0
    assert acc["source"]


async def test_outcome_rows_never_rewritten_by_override(client_with_flags):
    client, session, f_high, _f_med = client_with_flags
    scores_before = (await session.execute(
        select(Run.scores).where(Run.id == f_high.run_id)
    )).scalar_one()
    await client.patch(f"/flags/{f_high.id}/severity",
                       json={"severity": "Low"})
    scores_after = (await session.execute(
        select(Run.scores).where(Run.id == f_high.run_id)
    )).scalar_one()
    assert scores_after == scores_before  # audit trail untouched
    await client.patch(f"/flags/{f_high.id}/severity", json={"severity": None})
