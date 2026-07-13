"""
meta:
  purpose: Scorecard service (customize layer): CRUD over rules and their
           binary-check decompositions, plus load_rule_bundles — the
           DB-driven rule source for LIVE runs (corpus runs stay on the
           frozen seeded constants: they are the certification benchmark).
  contract: rule verbatim_text is stored EXACTLY as entered, never
            paraphrased (doc 05 doctrine extended to user rules). Adding a
            rule auto-decomposes (injected callable) into trigger +
            requirement checks and derives retrieval keyword families.
            Deleting a rule/check with existing flags raises Conflict
            (flags are audit rows; archival is day-2). Editing a rule's
            text re-decomposes only when regenerate=True (edits to
            severity alone never touch checks).
  deps: db models, pipeline.nodes.decompose.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shiboleth.db.models import BinaryCheck, Flag, Rule


class Conflict(RuntimeError):
    """Deletion blocked: flags reference this rule/check (audit trail)."""


async def get_scorecard(session: AsyncSession) -> list[dict]:
    rules = (await session.execute(
        select(Rule).order_by(Rule.position))).scalars().all()
    out = []
    for r in rules:
        checks = (await session.execute(
            select(BinaryCheck).where(BinaryCheck.rule_id == r.id)
            .order_by(BinaryCheck.kind.desc())  # trigger before requirement
        )).scalars().all()
        flag_count = (await session.execute(
            select(func.count(Flag.id)).where(
                Flag.check_id.in_([c.id for c in checks] or [""]))
        )).scalar() or 0
        out.append({
            "id": r.id, "verbatim_text": r.verbatim_text,
            "severity": r.severity, "position": r.position,
            "retrieval_keywords": r.retrieval_keywords or {},
            "seeded": not (r.retrieval_keywords or {}),
            "flag_count": flag_count,
            "checks": [{
                "id": c.id, "kind": c.kind, "text": c.text,
                "evidence_criteria": c.evidence_criteria,
                "library_entry_id": c.library_entry_id,
            } for c in checks],
        })
    return out


async def _next_rule_id(session: AsyncSession) -> tuple[str, int]:
    rules = (await session.execute(select(Rule))).scalars().all()
    nums = [int(r.id.split("-")[1]) for r in rules
            if r.id.startswith("R-") and r.id.split("-")[1].isdigit()]
    n = max(nums, default=0) + 1
    position = max((r.position for r in rules), default=0) + 1
    return f"R-{n:02d}", position


async def create_rule(session: AsyncSession, verbatim_text: str,
                      severity: str, decomposer) -> dict:
    scorecard_id = (await session.execute(
        select(Rule.scorecard_id).limit(1))).scalar() or "SC-01"
    rule_id, position = await _next_rule_id(session)
    d = decomposer(verbatim_text)
    rule = Rule(
        id=rule_id, scorecard_id=scorecard_id,
        verbatim_text=verbatim_text,  # stored exactly as entered
        severity=severity, position=position,
        retrieval_keywords={"primary": d.primary_keywords,
                            "broad": d.broad_keywords},
    )
    session.add(rule)
    await session.flush()  # rule row must exist before its checks (FK)
    session.add(BinaryCheck(id=f"{rule_id}-T", rule_id=rule_id,
                            kind="trigger", text=d.trigger_text,
                            evidence_criteria=d.trigger_criteria,
                            library_entry_id=None))
    session.add(BinaryCheck(id=f"{rule_id}-REQ", rule_id=rule_id,
                            kind="requirement", text=d.requirement_text,
                            evidence_criteria=d.requirement_criteria,
                            library_entry_id=None))
    await session.commit()
    return (await get_scorecard(session))[-1]


async def update_rule(session: AsyncSession, rule_id: str,
                      verbatim_text: str | None, severity: str | None,
                      regenerate: bool, decomposer=None) -> dict:
    rule = (await session.execute(
        select(Rule).where(Rule.id == rule_id))).scalar_one_or_none()
    if rule is None:
        raise LookupError(f"rule {rule_id} not found")
    if verbatim_text is not None:
        rule.verbatim_text = verbatim_text
    if severity is not None:
        rule.severity = severity
    if regenerate:
        if decomposer is None:
            raise ValueError("regenerate requires a decomposer")
        d = decomposer(rule.verbatim_text)
        checks = (await session.execute(
            select(BinaryCheck).where(BinaryCheck.rule_id == rule_id)
        )).scalars().all()
        by_kind = {c.kind: c for c in checks}
        if "trigger" in by_kind:
            by_kind["trigger"].text = d.trigger_text
            by_kind["trigger"].evidence_criteria = d.trigger_criteria
        if "requirement" in by_kind:
            by_kind["requirement"].text = d.requirement_text
            by_kind["requirement"].evidence_criteria = d.requirement_criteria
        if rule.retrieval_keywords:  # user rule: refresh derived keywords too
            rule.retrieval_keywords = {"primary": d.primary_keywords,
                                       "broad": d.broad_keywords}
    await session.commit()
    for r in await get_scorecard(session):
        if r["id"] == rule_id:
            return r
    raise LookupError(rule_id)


async def delete_rule(session: AsyncSession, rule_id: str) -> None:
    checks = (await session.execute(
        select(BinaryCheck).where(BinaryCheck.rule_id == rule_id)
    )).scalars().all()
    n_flags = (await session.execute(
        select(func.count(Flag.id)).where(
            Flag.check_id.in_([c.id for c in checks] or [""]))
    )).scalar() or 0
    if n_flags:
        raise Conflict(
            f"rule {rule_id} has {n_flags} flags on record; rules with "
            "findings cannot be deleted (archival is planned)")
    rule = (await session.execute(
        select(Rule).where(Rule.id == rule_id))).scalar_one_or_none()
    if rule is None:
        raise LookupError(f"rule {rule_id} not found")
    for c in checks:
        await session.delete(c)
    await session.delete(rule)
    await session.commit()


async def upsert_check(session: AsyncSession, rule_id: str,
                       check_id: str | None, kind: str, text: str,
                       evidence_criteria: str) -> dict:
    if check_id:
        check = (await session.execute(
            select(BinaryCheck).where(BinaryCheck.id == check_id)
        )).scalar_one_or_none()
        if check is None:
            raise LookupError(f"check {check_id} not found")
        check.text = text
        check.evidence_criteria = evidence_criteria
    else:
        existing = (await session.execute(
            select(func.count(BinaryCheck.id)).where(
                BinaryCheck.rule_id == rule_id))).scalar() or 0
        check = BinaryCheck(id=f"{rule_id}-X{existing + 1}", rule_id=rule_id,
                            kind=kind, text=text,
                            evidence_criteria=evidence_criteria,
                            library_entry_id=None)
        session.add(check)
    await session.commit()
    return {"id": check.id, "kind": check.kind, "text": check.text,
            "evidence_criteria": check.evidence_criteria}


async def delete_check(session: AsyncSession, check_id: str) -> None:
    n_flags = (await session.execute(
        select(func.count(Flag.id)).where(Flag.check_id == check_id)
    )).scalar() or 0
    if n_flags:
        raise Conflict(f"check {check_id} has {n_flags} flags on record")
    check = (await session.execute(
        select(BinaryCheck).where(BinaryCheck.id == check_id)
    )).scalar_one_or_none()
    if check is None:
        raise LookupError(f"check {check_id} not found")
    await session.delete(check)
    await session.commit()


async def load_rule_bundles(session: AsyncSession) -> list[dict]:
    """DB-driven rule bundles for LIVE runs: [{rule, checks, library,
    keywords}]. Library linkage follows checks.library_entry_id (D-01)."""
    from shiboleth.db.seed_rules import D01_APPROVED_TEXT

    bundles = []
    for r in await get_scorecard(session):
        library = None
        if any(c["library_entry_id"] == "D-01" for c in r["checks"]):
            library = {"id": "D-01", "approved_text": D01_APPROVED_TEXT}
        bundles.append({
            "rule": {"id": r["id"], "verbatim_text": r["verbatim_text"],
                     "severity": r["severity"]},
            "checks": r["checks"],
            "library": library,
            "keywords": r["retrieval_keywords"] or None,
        })
    return bundles
