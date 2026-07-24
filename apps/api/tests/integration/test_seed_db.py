"""
meta:
  purpose: Integration test for the M1 seed (needs docker Postgres). Seeds a
           dedicated test database and asserts Aarvin's M1 requirement at the
           STRONGEST level: the rule text READ BACK FROM THE DATABASE matches
           doc 05 §1 byte-for-byte. Also verifies decomposition shape, D-01,
           product/properties, and idempotency (double-seed).
  contract: creates/drops shiboleth_test tables per run via alembic; skipped
            when Postgres or doc 05 is unavailable.
  deps: pytest, alembic, asyncpg, docker Postgres from code/docker-compose.yml.
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from adlign.db.models import BinaryCheck, LibraryEntry, Product, Property, Rule
from adlign.db.seed import CHECKS, seed
from adlign.db.seed_rules import D01_APPROVED_TEXT
from tests.unit.test_seed_verbatim import DOC05, extract_rules_from_doc05

API_DIR = Path(__file__).resolve().parents[2]
TEST_URL = "postgresql+asyncpg://shiboleth:shiboleth@localhost:5432/shiboleth_test"


def _postgres_available() -> bool:
    import socket

    try:
        with socket.create_connection(("localhost", 5432), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


@pytest.fixture
async def seeded_session():
    # create the test database (idempotent), migrate, seed
    import asyncpg

    admin = await asyncpg.connect(
        user="shiboleth", password="shiboleth", database="postgres", host="localhost"
    )
    exists = await admin.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = 'shiboleth_test'"
    )
    if not exists:
        await admin.execute("CREATE DATABASE shiboleth_test")
    await admin.close()

    engine = create_async_engine(TEST_URL)
    from adlign.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # drop_all only covers model tables; without this, a stale
        # alembic_version makes the next upgrade a no-op on an empty DB
        from sqlalchemy import text

        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    os.environ["ALEMBIC_DATABASE_URL"] = TEST_URL
    try:
        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(API_DIR / "migrations"))
        await engine.dispose()
        # env.py calls asyncio.run(); give it its own thread (and loop)
        import asyncio

        await asyncio.to_thread(command.upgrade, config, "head")
    finally:
        os.environ.pop("ALEMBIC_DATABASE_URL", None)

    engine = create_async_engine(TEST_URL)
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed(session)
        yield session
    await engine.dispose()


@pytest.mark.skipif(not DOC05.exists(), reason="doc 05 not present")
async def test_db_rule_text_matches_doc05_byte_for_byte(seeded_session):
    """Aarvin's M1 requirement: seeded rule text vs doc 05 §1, byte-for-byte,
    read back from Postgres (round-trip through driver + storage included)."""
    doc_rules = extract_rules_from_doc05()
    rows = (
        (await seeded_session.execute(select(Rule).order_by(Rule.position)))
        .scalars()
        .all()
    )
    assert len(rows) == len(doc_rules) == 4
    for row, doc_text in zip(rows, doc_rules):
        assert row.verbatim_text == doc_text, f"{row.id} drifted in the DB"
        assert row.verbatim_text.encode("utf-8") == doc_text.encode("utf-8")


async def test_decomposition_shape(seeded_session):
    rows = (await seeded_session.execute(select(BinaryCheck))).scalars().all()
    assert len(rows) == len(CHECKS) == 8
    by_rule: dict[str, set[str]] = {}
    for check in rows:
        by_rule.setdefault(check.rule_id, set()).add(check.kind)
    # every rule -> exactly one trigger + one requirement
    assert by_rule == {f"R-0{i}": {"trigger", "requirement"} for i in range(1, 5)}


async def test_d01_seeded_and_linked(seeded_session):
    entry = await seeded_session.get(LibraryEntry, "D-01")
    assert entry is not None
    assert entry.approved_text == D01_APPROVED_TEXT
    assert entry.status == "approved"
    r01_req = await seeded_session.get(BinaryCheck, "R-01-REQ")
    assert r01_req.library_entry_id == "D-01"


async def test_product_and_properties(seeded_session):
    product = await seeded_session.get(Product, "turbotax-free")
    assert product.name == "TurboTax Free"
    props = (
        (await seeded_session.execute(select(Property))).scalars().all()
    )
    assert {p.kind for p in props} == {"website", "instagram", "facebook"}
    website = next(p for p in props if p.kind == "website")
    assert website.config == {"depth": 2, "page_cap": 20}


async def test_seed_idempotent(seeded_session):
    counts = await seed(seeded_session)  # second run over same session/db
    assert counts["rules"] == 4 and counts["checks"] == 8
    rows = (await seeded_session.execute(select(Rule))).scalars().all()
    assert len(rows) == 4  # no duplicates


async def test_flag_has_trust_signal_columns(seeded_session):
    """Stage 1: flags carry the two structural trust signals as columns."""
    from sqlalchemy import inspect as sa_inspect

    conn = await seeded_session.connection()
    names = await conn.run_sync(
        lambda sync_conn: {c["name"] for c in sa_inspect(sync_conn).get_columns("flags")}
    )
    assert {"evidence_valid", "ambiguous"} <= names
