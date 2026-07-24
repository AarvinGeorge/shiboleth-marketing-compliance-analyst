"""
meta:
  purpose: Stage 1 trust: GET /products/{id} flags each carry a `trust` object.
           Certified rules -> kind "measured"; custom rules (no ground-truth
           accuracy) -> kind "reliability" from the structural badge. Advisory
           only; verdicts/scores unchanged.
  contract: every flag payload has trust = {kind, label, detail}.
  deps: docker Postgres (skipped when down); seeded test DB fixture.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from adlign.db.models import BinaryCheck, Flag, Material, Rule, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


@pytest.fixture
async def client_with_flags(seeded_session):  # noqa: F811
    run = Run(product_id="turbotax-free", mode="corpus", status="completed",
              scores={"draft": 50.0, "verified": 50.0})
    seeded_session.add(run)
    await seeded_session.flush()

    material = Material(property_id="tt-website", ref="https://x/", kind="page",
                        content_hash="h-trust", extracted_text="File free.")
    seeded_session.add(material)

    # a custom rule + check that has no measured accuracy
    seeded_session.add(Rule(id="R-99", scorecard_id="SC-01",
                            verbatim_text="Custom rule text.", severity="Medium",
                            position=99))
    await seeded_session.flush()
    seeded_session.add(BinaryCheck(id="R-99-REQ", rule_id="R-99", kind="requirement",
                                   text="req", evidence_criteria="ec"))
    await seeded_session.flush()

    # certified-rule flag (R-01) -> measured; custom-rule flag (R-99) -> reliability
    seeded_session.add_all([
        Flag(run_id=run.id, material_id=material.id, check_id="R-01-REQ",
             axis_a=False, axis_b=False, intersection_tag="unapproved_violation",
             evidence_quote="File free.", location="hero", reason="r",
             confidence=0.9, state="open", evidence_valid=True, ambiguous=False,
             verifier_agrees=True, verifier_model="openai:test",
             verifier_reason="second reviewer agrees"),
        Flag(run_id=run.id, material_id=material.id, check_id="R-99-REQ",
             axis_a=False, axis_b=False, intersection_tag="unapproved_violation",
             evidence_quote="File free.", location="hero", reason="r",
             confidence=0.9, state="open", evidence_valid=True, ambiguous=False),
    ])
    await seeded_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from adlign.main import create_app

    app = create_app()
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


async def test_every_flag_has_a_trust_object(client_with_flags):
    r = await client_with_flags.get("/products/turbotax-free")
    assert r.status_code == 200, r.text
    flags = r.json()["flags"]
    assert flags
    for f in flags:
        assert "trust" in f
        assert f["trust"]["kind"] in ("measured", "verifier", "reliability")
        assert f["trust"]["label"]


async def test_certified_rule_is_measured_custom_is_reliability(client_with_flags):
    r = await client_with_flags.get("/products/turbotax-free")
    by_check = {f["verdicts"]["check_id"]: f["trust"] for f in r.json()["flags"]}
    assert by_check["R-01-REQ"]["kind"] == "measured"
    assert "measured" in by_check["R-01-REQ"]["label"].lower()
    assert by_check["R-99-REQ"]["kind"] == "reliability"
    assert by_check["R-99-REQ"]["label"] == "Reliability: strong"


async def test_flag_payload_carries_verifier_when_present(client_with_flags):
    r = await client_with_flags.get("/products/turbotax-free")
    by_check = {f["verdicts"]["check_id"]: f.get("verifier") for f in r.json()["flags"]}
    assert by_check["R-01-REQ"] == {"agrees": True, "reason": "second reviewer agrees"}
    assert by_check["R-99-REQ"] is None  # never verified -> absent
