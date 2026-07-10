"""
meta:
  purpose: Product routes (01_spec §6): list + detail. Detail carries what U6
           renders: product, properties, latest run scores, flags with
           verdicts + cluster labels.
  contract: GET /products; GET /products/{id} -> {product, properties, scores,
            flags[]}. Read-only; disposition lives in flags.py.
  deps: db models only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import desc, select

from shiboleth.db.models import Cluster, Flag, Product, Property, Run

router = APIRouter()


@router.get("/products")
async def list_products(request: Request) -> list[dict]:
    async with request.app.state.session_factory() as session:
        products = (await session.execute(select(Product))).scalars().all()
        out = []
        for p in products:
            latest = (await session.execute(
                select(Run).where(Run.product_id == p.id)
                .order_by(desc(Run.started_at)).limit(1)
            )).scalar_one_or_none()
            scores = latest.scores if latest else None
            if scores:  # outcome_rows is recompute bookkeeping, not payload
                scores = {k: v for k, v in scores.items() if k != "outcome_rows"}
            out.append({"id": p.id, "name": p.name, "status": p.status,
                        "scores": scores, "run_id": latest.id if latest else None,
                        "last_run_status": latest.status if latest else None})
        return out


@router.get("/products/{product_id}")
async def product_detail(product_id: str, request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        product = await session.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "product not found")
        properties = (await session.execute(
            select(Property).where(Property.product_id == product_id)
        )).scalars().all()
        latest = (await session.execute(
            select(Run).where(Run.product_id == product_id)
            .order_by(desc(Run.started_at)).limit(1)
        )).scalar_one_or_none()
        flags: list[dict] = []
        clusters: dict[str, str] = {}
        if latest:
            rows = (await session.execute(
                select(Flag).where(Flag.run_id == latest.id)
            )).scalars().all()
            cluster_rows = (await session.execute(
                select(Cluster).where(Cluster.run_id == latest.id)
            )).scalars().all()
            clusters = {c.id: c.label for c in cluster_rows}
            for f in rows:
                flags.append({
                    "id": f.id, "state": f.state, "assigned_team": f.assigned_team,
                    "note": f.note, "cluster_id": f.cluster_id,
                    "cluster_label": clusters.get(f.cluster_id),
                    "material_id": f.material_id, "location": f.location,
                    "verdicts": {
                        "check_id": f.check_id, "axis_a": f.axis_a,
                        "axis_b": f.axis_b, "intersection_tag": f.intersection_tag,
                        "evidence_quote": f.evidence_quote, "reason": f.reason,
                        "confidence": f.confidence,
                    },
                })
        scores = latest.scores if latest else None
        if scores:
            scores = {k: v for k, v in scores.items() if k != "outcome_rows"}
        return {
            "product": {"id": product.id, "name": product.name,
                        "status": product.status},
            "run_id": latest.id if latest else None,  # why-flagged chain source
            "model_config": latest.model_config_json if latest else None,
            "properties": [
                {"id": p.id, "kind": p.kind, "url_or_handle": p.url_or_handle,
                 "config": p.config} for p in properties
            ],
            "scores": scores,
            "flags": flags,
        }


@router.get("/extract-properties")
async def extract_properties_route(text: str) -> list[dict]:
    """U3 live chips (01_spec §6). Deterministic parse; LLM pass reserved
    for the run-creation path where latency matters less."""
    from shiboleth.services.ingestion.extract import extract_properties

    return [d.model_dump() for d in extract_properties(text, invoke=None)]
