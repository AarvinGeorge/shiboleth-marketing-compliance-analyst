"""
meta:
  purpose: One-off backfill of flags.evidence_valid for flags written before the
           column existed. Recomputes the whitespace-tolerant substring check
           (evidence_in_material) of each flag's evidence_quote against its
           material's extracted_text. Idempotent: only touches rows where
           evidence_valid IS NULL. Advisory data only: never changes a verdict,
           score, or state.
  contract: python -m adlign.scripts.backfill_evidence_valid
  deps: adlign.config, adlign.db.engine, adlign.db.models,
        adlign.pipeline.nodes.check.evidence_in_material.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from adlign.config import load_settings
from adlign.db.engine import get_engine, session_factory
from adlign.db.models import Flag, Material
from adlign.pipeline.nodes.check import evidence_in_material


async def backfill() -> int:
    settings = load_settings()
    engine = get_engine(settings.database_url)
    async with session_factory(engine)() as session:
        flags = (
            await session.execute(select(Flag).where(Flag.evidence_valid.is_(None)))
        ).scalars().all()
        n = 0
        for f in flags:
            if not f.material_id:
                continue
            material = await session.get(Material, f.material_id)
            if material is None:
                continue
            f.evidence_valid = evidence_in_material(f.evidence_quote, material.extracted_text)
            n += 1
        await session.commit()
        return n


async def _main() -> None:
    n = await backfill()
    print(f"backfilled evidence_valid on {n} flags")


if __name__ == "__main__":
    asyncio.run(_main())
