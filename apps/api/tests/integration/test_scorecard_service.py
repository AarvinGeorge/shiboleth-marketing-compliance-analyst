"""
meta:
  purpose: Integration tests for the customize-scorecard layer: rule CRUD
           with a FAKE decomposer (CI never calls an LLM), keyword storage,
           deletion guards, and load_rule_bundles (the live-run rule source).
  contract: verbatim text stored exactly as entered; new rule gets trigger +
            requirement checks and keyword families; delete blocked only
            when flags reference the rule; seeded rules load with registry
            keywords (None) and user rules with their DB families.
  deps: pytest, docker Postgres (shiboleth_test db) via the seeded_session
        fixture from test_seed_db.
"""

import pytest

from shiboleth.pipeline.nodes.decompose import Decomposition
from shiboleth.services.scorecard import (Conflict, create_rule, delete_rule,
                                          get_scorecard, load_rule_bundles,
                                          update_rule)
from tests.integration.test_seed_db import (  # noqa: F401 — fixture import
    _postgres_available,
    seeded_session,
)

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)

RULE_TEXT = ("If a cashback offer is advertised, the advertisement must state "
             "the maximum cashback percentage and any category  limits.")


def fake_decomposer(rule_text: str) -> Decomposition:
    return Decomposition(
        trigger_text="Does the material advertise a cashback offer?",
        trigger_criteria="A cashback offer for the advertised product; quote it.",
        requirement_text="Are the maximum percentage and category limits stated?",
        requirement_criteria="Both the max percentage and limits present; quote them.",
        primary_keywords=["cashback", "cash back"],
        broad_keywords=["percent"],
    )


@pytest.mark.asyncio
async def test_rule_lifecycle_and_bundles(seeded_session):  # noqa: F811
    session = seeded_session

    # create: verbatim preserved (incl. the double space), checks + keywords derived
    created = await create_rule(session, RULE_TEXT, "Medium", fake_decomposer)
    assert created["verbatim_text"] == RULE_TEXT
    assert created["id"] == "R-05"
    assert {c["kind"] for c in created["checks"]} == {"trigger", "requirement"}
    assert created["retrieval_keywords"]["primary"] == ["cashback", "cash back"]
    assert created["seeded"] is False

    # seeded rules keep empty keywords (registry-driven)
    scorecard = await get_scorecard(session)
    r01 = next(r for r in scorecard if r["id"] == "R-01")
    assert r01["seeded"] is True

    # bundles: live-run source — user rule carries its families
    bundles = await load_rule_bundles(session)
    by_id = {b["rule"]["id"]: b for b in bundles}
    assert by_id["R-05"]["keywords"]["primary"] == ["cashback", "cash back"]
    assert by_id["R-01"]["keywords"] is None  # registry fallback
    assert by_id["R-01"]["library"]["id"] == "D-01"
    assert by_id["R-05"]["library"] is None

    # edit severity only: checks untouched
    updated = await update_rule(session, "R-05", None, "High", regenerate=False)
    assert updated["severity"] == "High"
    assert {c["kind"] for c in updated["checks"]} == {"trigger", "requirement"}

    # delete: allowed (no flags reference it)
    await delete_rule(session, "R-05")
    assert all(r["id"] != "R-05" for r in await get_scorecard(session))

    # deletion guard: attach a flag to R-01 and assert Conflict
    from shiboleth.db.models import Flag, Run
    run = Run(product_id="turbotax-free", mode="corpus", status="done")
    session.add(run)
    await session.flush()
    session.add(Flag(run_id=run.id, material_id=None, check_id="R-01-REQ",
                     axis_a=False, axis_b=None,
                     intersection_tag="unapproved_violation",
                     evidence_quote="q", reason="r", confidence=0.9))
    await session.flush()
    with pytest.raises(Conflict):
        await delete_rule(session, "R-01")
