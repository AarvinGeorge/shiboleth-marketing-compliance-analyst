"""
meta:
  purpose: Run routes (01_spec §6): POST /checks (corpus mode now; live mode
           gains N1/N2 at M6), GET /runs/{id}/events as SSE (07 §6: events
           are persisted rows FIRST; this endpoint tails the rows), and a
           plain JSON events list for the U7 why-flagged chain.
  contract: POST /checks {product_id, mode: corpus} -> {run_id} (corpus runs
            synchronously reuse the E3 cache, so they are fast and $0 after
            certification). SSE replays persisted events then polls for new
            rows until run_finished (DB-as-checkpoint: works across process
            restarts, matching the 07 §2 pause/resume doctrine).
  deps: db models, corpus_run, sse-starlette.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from shiboleth.db.models import Event, Run

router = APIRouter()


class CheckRequest(BaseModel):
    product_id: str
    mode: str = "corpus"  # live arrives at M6


@router.post("/checks")
async def start_check(body: CheckRequest, request: Request) -> dict:
    if body.mode != "corpus":
        raise HTTPException(422, "live mode lands at M6; use mode=corpus")
    app = request.app
    settings = app.state.settings

    from shiboleth.evals.harnesses.e3 import PacedCachedInvoke
    from shiboleth.pipeline.corpus_run import run_corpus
    from shiboleth.pipeline.nodes.cluster import groq_labeler

    invoke = PacedCachedInvoke(settings.model_for("check"))
    labeler = groq_labeler(settings.model_for("cluster_label"))
    async with app.state.session_factory() as session:
        run_id = await run_corpus(session, invoke, labeler,
                                  product_id=body.product_id)
    return {"run_id": run_id}


@router.get("/runs/{run_id}/events")
async def run_events_sse(run_id: str, request: Request) -> EventSourceResponse:
    session_factory = request.app.state.session_factory

    async def stream():
        seen: set[str] = set()
        while True:
            async with session_factory() as session:
                run = await session.get(Run, run_id)
                if run is None:
                    yield {"event": "error", "data": json.dumps({"message": "run not found"})}
                    return
                rows = (await session.execute(
                    select(Event).where(Event.run_id == run_id).order_by(Event.ts)
                )).scalars().all()
            for row in rows:
                if row.id in seen:
                    continue
                seen.add(row.id)
                yield {
                    "event": row.event_type,
                    "id": row.id,
                    "data": json.dumps({
                        "event_id": row.id, "run_id": run_id,
                        "ts": row.ts.isoformat(), "type": row.event_type,
                        "node": row.node, "property_id": row.property_id,
                        "flag_id": row.flag_id, "payload": row.payload,
                    }),
                }
            if any(r.event_type in ("run_finished", "error") for r in rows):
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(1.0)

    return EventSourceResponse(stream())


@router.get("/runs/{run_id}/events.json")
async def run_events_json(run_id: str, request: Request) -> list[dict]:
    async with request.app.state.session_factory() as session:
        rows = (await session.execute(
            select(Event).where(Event.run_id == run_id).order_by(Event.ts)
        )).scalars().all()
        return [
            {"event_id": r.id, "type": r.event_type, "node": r.node,
             "flag_id": r.flag_id, "ts": r.ts.isoformat(), "payload": r.payload}
            for r in rows
        ]
