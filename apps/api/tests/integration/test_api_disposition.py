"""
meta:
  purpose: Integration tests (first) for the M4 core: disposition endpoint
           (S3 choreography, 07 §3) — lifecycle validation, verified-score
           recompute, eval_items append (dismissed = FP label) — plus
           GET /products/{id} shape.
  contract: POST /flags/{id}/disposition {action, team?, note?} returns the
            updated flag + recomputed scores; illegal transitions are 409;
            dismissal appends an eval_items row with source=disposition.
  deps: docker Postgres (skipped when down); reuses the seeded test DB
        fixture pattern from test_seed_db.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from adlign.db.models import EvalItem, Flag, Material, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


@pytest.fixture
async def client_with_flag(seeded_session):  # noqa: F811
    """App wired to the seeded test DB + one open flag on a corpus run."""
    run = Run(product_id="turbotax-free", mode="corpus", status="completed")
    seeded_session.add(run)
    await seeded_session.flush()
    material = Material(property_id="tt-website", ref="https://x/", kind="page",
                        content_hash="h1", extracted_text="File free with TaxCo.")
    seeded_session.add(material)
    await seeded_session.flush()
    flag = Flag(run_id=run.id, material_id=material.id, check_id="R-01-REQ",
                axis_a=False, axis_b=False, intersection_tag="unapproved_violation",
                evidence_quote="File free with TaxCo.", location="hero",
                reason="no disclosure", confidence=0.9, state="open")
    seeded_session.add(flag)
    await seeded_session.flush()
    # persisted outcome rows: one High flag + one High pass -> draft 50.0;
    # dismissing the flag rescores it as pass -> verified 100.0
    run.scores = {
        "draft": 50.0, "verified": 50.0, "per_property": {"tt-website": 50.0},
        "outcome_rows": [
            {"verdict_status": "flag", "severity": "High",
             "property_id": "tt-website", "flag_id": flag.id},
            {"verdict_status": "pass", "severity": "High",
             "property_id": "tt-website", "flag_id": None},
        ],
    }
    await seeded_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from adlign.main import create_app

    app = create_app()
    # httpx ASGITransport does not run lifespan; wire state directly.
    # Fresh engine per test: the cached get_engine pool holds connections
    # across tests while the fixture drops tables underneath them.
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, flag, run, seeded_session
    await engine.dispose()


async def test_confirm_then_assign_flow(client_with_flag):
    client, flag, run, session = client_with_flag
    r = await client.post(f"/flags/{flag.id}/disposition",
                          json={"action": "confirm", "team": "Web", "note": "real"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["flag"]["state"] == "assigned"  # confirm+team -> assigned
    assert body["flag"]["assigned_team"] == "Web"
    assert "scores" in body


async def test_dismiss_recomputes_verified_and_appends_eval_item(client_with_flag):
    client, flag, run, session = client_with_flag
    r = await client.post(f"/flags/{flag.id}/disposition",
                          json={"action": "dismiss", "note": "FP: covered elsewhere"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["flag"]["state"] == "dismissed"
    # dismissed flag rescored as pass -> verified above draft
    assert body["scores"]["verified"] == 100.0
    items = (await session.execute(
        EvalItem.__table__.select().where(EvalItem.source == "disposition")
    )).fetchall()
    assert len(items) == 1


async def test_illegal_transition_409(client_with_flag):
    client, flag, run, session = client_with_flag
    await client.post(f"/flags/{flag.id}/disposition", json={"action": "dismiss"})
    r = await client.post(f"/flags/{flag.id}/disposition", json={"action": "confirm"})
    assert r.status_code == 409


async def test_product_detail_shape(client_with_flag):
    client, flag, run, session = client_with_flag
    r = await client.get("/products/turbotax-free")
    assert r.status_code == 200
    body = r.json()
    assert body["product"]["name"] == "TurboTax Free"
    assert len(body["flags"]) == 1
    assert body["flags"][0]["verdicts"]["intersection_tag"] == "unapproved_violation"
    # source_url is the material's clean per-page URL for the "view original
    # source" link, distinct from the display-only location string.
    assert body["flags"][0]["source_url"] == "https://x/"
