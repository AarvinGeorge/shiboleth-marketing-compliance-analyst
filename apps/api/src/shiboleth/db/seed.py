"""
meta:
  purpose: Idempotent seed script (M1): the VERBATIM 4-rule scorecard
           (generated seed_rules.py, byte-for-byte from doc 05 §1), its
           approved trigger+requirement decomposition, library entry D-01,
           and product TurboTax Free with its three properties. Seed data is
           DATA — no TurboTax logic in code (guardrail 1).
  contract: seed(session) upserts by deterministic natural ids (SC-01, R-0x,
            R-0x-T/R-0x-REQ, D-01, turbotax-free, tt-*); safe to re-run.
            Run: uv run python -m shiboleth.db.seed
  deps: sqlalchemy, shiboleth.db.models, shiboleth.db.seed_rules (generated).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shiboleth.db.models import (
    BinaryCheck,
    LibraryEntry,
    Product,
    Property,
    Rule,
    Scorecard,
)
from shiboleth.db.seed_rules import D01_APPROVED_TEXT, RULES

SCORECARD_ID = "SC-01"
PRODUCT_ID = "turbotax-free"

# Approved decomposition: one trigger + one requirement per rule, phrased from
# the rule text + the frozen ground-truth reasoning patterns. R-04's trigger
# carries the exemption (S17: general statements do not trigger).
CHECKS: list[dict] = [
    {
        "id": "R-01-T", "rule_id": "R-01", "kind": "trigger",
        "text": "Does the material mention TurboTax Free (the free product or free filing offer)?",
        "evidence_criteria": "A mention of TurboTax Free / Free Edition / filing free with TurboTax; quote the mention verbatim.",
        "library_entry_id": None,
    },
    {
        "id": "R-01-REQ", "rule_id": "R-01", "kind": "requirement",
        "text": "Is the eligibility disclosure (D-01) present right underneath the free mention?",
        "evidence_criteria": "The disclosure text matching D-01 positioned directly beneath/adjacent to the free claim; quote the disclosure as published (position matters: 'right underneath' is an attribution requirement).",
        "library_entry_id": "D-01",
    },
    {
        "id": "R-02-T", "rule_id": "R-02", "kind": "trigger",
        "text": "Is a rate of finance charge stated?",
        "evidence_criteria": "A numeric rate describing the cost of credit (loan fee rate, finance charge percentage); quote the rate in context.",
        "library_entry_id": None,
    },
    {
        "id": "R-02-REQ", "rule_id": "R-02", "kind": "requirement",
        "text": "Is the finance charge stated as an APR?",
        "evidence_criteria": "The stated rate is expressed as an APR using that term; quote the APR statement.",
        "library_entry_id": None,
    },
    {
        "id": "R-03-T", "rule_id": "R-03", "kind": "trigger",
        "text": "Is the product being advertised a deposit product?",
        "evidence_criteria": "The advertised product is a checking/savings/deposit account (money held on deposit), not a loan or tax service; quote the product description.",
        "library_entry_id": None,
    },
    {
        "id": "R-03-REQ", "rule_id": "R-03", "kind": "requirement",
        "text": "Does the FDIC insurance language state the deposit product is FDIC-insured up to $250,000 through the named bank?",
        "evidence_criteria": "FDIC language matching the required formulation: FDIC-insured, the $250,000 limit, and the partner bank named; quote the FDIC statement as published.",
        "library_entry_id": None,
    },
    {
        "id": "R-04-T", "rule_id": "R-04", "kind": "trigger",
        "text": "Does the advertisement state a specific bonus (general statements such as 'bonus checking' or 'get a bonus when you open a checking account' do not trigger)?",
        "evidence_criteria": "A concrete bonus offer (amount, reward, or promotion terms). General bonus mentions without specifics are the exemption: not triggered. Quote the bonus statement.",
        "library_entry_id": None,
    },
    {
        "id": "R-04-REQ", "rule_id": "R-04", "kind": "requirement",
        "text": "Does the advertisement state clearly and conspicuously, as applicable: (1) 'Annual percentage yield' using that term; (2) time requirement to obtain the bonus; (3) minimum balance required to obtain the bonus; (4) minimum balance to open the account if greater; (5) when the bonus will be provided?",
        "evidence_criteria": "Each applicable item present clearly and conspicuously near the bonus offer; quote what is present and name what is missing.",
        "library_entry_id": None,
    },
]

PROPERTIES: list[dict] = [
    {
        "id": "tt-website", "kind": "website",
        "url_or_handle": "https://turbotax.intuit.com/",
        "config": {"depth": 2, "page_cap": 20},
    },
    {
        "id": "tt-instagram", "kind": "instagram",
        "url_or_handle": "instagram.com/turbotax",
        "config": {"timeframe": {"from": "2026-02-01", "to": "2026-03-31"}},
    },
    {
        "id": "tt-facebook", "kind": "facebook",
        "url_or_handle": "facebook.com/turbotax",
        "config": {"timeframe": {"from": "2026-02-01", "to": "2026-03-31"}},
    },
]


async def _upsert(session: AsyncSession, model, values: dict) -> None:
    existing = await session.get(model, values["id"])
    if existing is None:
        session.add(model(**values))
    else:
        for key, value in values.items():
            setattr(existing, key, value)


async def seed(session: AsyncSession) -> dict[str, int]:
    await _upsert(session, Scorecard, {
        "id": SCORECARD_ID, "name": "Shibboleth bank-partner scorecard", "version": 1,
    })
    for rule_id, verbatim_text, severity, position in RULES:
        await _upsert(session, Rule, {
            "id": rule_id, "scorecard_id": SCORECARD_ID,
            "verbatim_text": verbatim_text, "severity": severity, "position": position,
        })
    await _upsert(session, LibraryEntry, {
        "id": "D-01", "kind": "disclosure",
        "title": "TurboTax Free eligibility disclosure",
        "approved_text": D01_APPROVED_TEXT, "status": "approved",
        "provenance": {"source": "doc 05 §2 (company demo brief)"},
    })
    for check in CHECKS:
        await _upsert(session, BinaryCheck, check)
    await _upsert(session, Product, {
        "id": PRODUCT_ID, "name": "TurboTax Free", "status": "active",
    })
    for prop in PROPERTIES:
        await _upsert(session, Property, {**prop, "product_id": PRODUCT_ID})
    await session.commit()
    return {
        "scorecards": 1, "rules": len(RULES), "checks": len(CHECKS),
        "library_entries": 1, "products": 1, "properties": len(PROPERTIES),
    }


async def _main() -> None:
    from shiboleth.config import load_settings
    from shiboleth.db.engine import get_engine, session_factory

    settings = load_settings()
    engine = get_engine(settings.database_url)
    async with session_factory(engine)() as session:
        counts = await seed(session)
    print(f"Seeded: {counts}")

    # read-back proof: rule text in the DB is byte-identical to seed_rules
    from sqlalchemy import select as sync_select  # noqa: F401
    async with session_factory(engine)() as session:
        rows = (await session.execute(select(Rule).order_by(Rule.position))).scalars().all()
        for row, (rule_id, verbatim_text, _sev, _pos) in zip(rows, RULES):
            status = "OK" if row.verbatim_text == verbatim_text else "MISMATCH"
            print(f"  {row.id}: verbatim {status} ({len(row.verbatim_text)} chars)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
