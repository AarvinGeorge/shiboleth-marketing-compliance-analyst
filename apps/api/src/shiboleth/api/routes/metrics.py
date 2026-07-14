"""
meta:
  purpose: GET /metrics — the dashboard hero data (metrics overhaul
           2026-07-13: open-flags donut by tag + open-violations tile,
           portfolio-wide) computed from the REAL database (no fixtures).
           Also POST /products (create product + properties from New-check
           chips). Every number traces to a SQL aggregate over current DB
           state (KPI traceability, E3).
  contract: GET /metrics -> {open_flags_total, open_flags_by_tag,
            open_violations, open_violations_high,
            open_violations_by_severity: {High, Medium, Low}}. The severity
            partition sums to open_violations. Scope: each product's
            LATEST run only (multiple runs per product would double count;
            the dashboard product cards show the latest run and these
            numbers must equal them exactly). Definitions: open flag =
            flags.state='open'; needs_review = open flag whose persisted
            outcome verdict_status is 'needs_review'; open violation = open
            flag with a violation verdict, i.e. every open flag that is NOT
            needs_review. POST /products {name, properties:[...]} -> {id}.
  deps: db models.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select

from shiboleth.db.models import Flag, Product, Property, Run, new_id

router = APIRouter()

SEVERITY_BY_RULE = {"R-01": "High", "R-02": "High", "R-03": "Medium", "R-04": "Medium"}


def _severity(check_id: str) -> str:
    return SEVERITY_BY_RULE.get(check_id.rsplit("-", 1)[0], "Medium")


async def _latest_runs(session) -> list[Run]:
    """The latest run per product (any status). Metric surfaces read from the
    product's most recent run, matching what the dashboard card shows."""
    products = (await session.execute(select(Product))).scalars().all()
    runs = []
    for p in products:
        r = (await session.execute(
            select(Run).where(Run.product_id == p.id)
            .order_by(desc(Run.started_at)).limit(1)
        )).scalar_one_or_none()
        if r is not None:
            runs.append(r)
    return runs


def needs_review_flag_ids(run: Run) -> set[str]:
    """Flag ids the run's persisted outcome rows mark needs_review (the
    checker declined to decide; excluded from the score denominator and NOT
    a violation)."""
    return {
        row.get("flag_id")
        for row in (run.scores or {}).get("outcome_rows", [])
        if row.get("verdict_status") == "needs_review" and row.get("flag_id")
    }


async def compute_portfolio_metrics(session) -> dict:
    """Portfolio-wide open-flag picture over each product's LATEST run only.
    Donut buckets partition ALL open flags: unapproved_violation /
    drifted_but_compliant / needs_review / other (remaining tags). The tile:
    open_violations = open flags with a violation verdict (total minus
    needs_review), so donut total and tile stay mutually consistent AND
    equal to what the product surfaces show."""
    latest = await _latest_runs(session)
    by_tag = {"unapproved_violation": 0, "drifted_but_compliant": 0,
              "needs_review": 0, "other": 0}
    by_severity = {"High": 0, "Medium": 0, "Low": 0}
    open_total = 0
    violations = 0
    for r in latest:
        review_ids = needs_review_flag_ids(r)
        flags = (await session.execute(
            select(Flag).where(Flag.run_id == r.id, Flag.state == "open")
        )).scalars().all()
        for f in flags:
            open_total += 1
            if f.id in review_ids:
                by_tag["needs_review"] += 1
                continue
            if f.intersection_tag in ("unapproved_violation",
                                      "drifted_but_compliant"):
                by_tag[f.intersection_tag] += 1
            else:
                by_tag["other"] += 1
            violations += 1
            sev = _severity(f.check_id)
            by_severity[sev if sev in by_severity else "Medium"] += 1
    return {
        "open_flags_total": open_total,
        "open_flags_by_tag": by_tag,
        "open_violations": violations,
        "open_violations_high": by_severity["High"],
        "open_violations_by_severity": by_severity,
    }


@router.get("/metrics")
async def get_metrics(request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        return await compute_portfolio_metrics(session)


class NewProperty(BaseModel):
    kind: str
    url_or_handle: str
    config: dict = {}


class NewProduct(BaseModel):
    name: str
    properties: list[NewProperty] = []


@router.post("/products", status_code=201)
async def create_product(body: NewProduct, request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        existing = (await session.execute(
            select(Product).where(Product.name == body.name)
        )).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(409, f"product '{body.name}' already exists")
        product = Product(id=new_id(), name=body.name, status="active")
        session.add(product)
        await session.flush()
        for prop in body.properties:
            session.add(Property(id=new_id(), product_id=product.id, kind=prop.kind,
                                 url_or_handle=prop.url_or_handle, config=prop.config))
        await session.commit()
        return {"id": product.id, "name": product.name}
