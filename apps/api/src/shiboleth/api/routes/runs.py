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

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from shiboleth.db.models import Event, Run

router = APIRouter()


class CheckRequest(BaseModel):
    product_id: str
    mode: str = "corpus"  # live arrives at M6


def _pipeline_deps(settings):
    from shiboleth.evals.harnesses.e3 import PacedCachedInvoke
    from shiboleth.pipeline.nodes.cluster import groq_labeler

    return (PacedCachedInvoke(settings.model_for("check")),
            groq_labeler(settings.model_for("cluster_label")))


@router.post("/checks")
async def start_check(body: CheckRequest, request: Request) -> dict:
    app = request.app
    invoke, labeler = _pipeline_deps(app.state.settings)

    if body.mode == "corpus":
        from shiboleth.pipeline.corpus_run import run_corpus

        async with app.state.session_factory() as session:
            run_id = await run_corpus(session, invoke, labeler,
                                      product_id=body.product_id)
        return {"run_id": run_id}

    # live (07 §3 S1): the run row is created + committed HERE so the caller
    # gets its id immediately; one in-process async task then owns ingest.
    # The barrier may park it as awaiting_input; paste/skip endpoints resume.
    from shiboleth.pipeline.live_run import create_live_run, start_live_run

    async with app.state.session_factory() as session:
        run_id = await create_live_run(session, body.product_id)

    async def task():
        async with app.state.session_factory() as session:
            await start_live_run(session, invoke, labeler,
                                 product_id=body.product_id, run_id=run_id)

    run_task = asyncio.create_task(task())
    app.state.live_tasks = getattr(app.state, "live_tasks", set())
    app.state.live_tasks.add(run_task)
    run_task.add_done_callback(app.state.live_tasks.discard)
    return {"run_id": run_id, "status": "started"}


class PasteRequest(BaseModel):
    property_id: str
    text: str


class SkipRequest(BaseModel):
    # skip carries no content: the UI sends {property_id} only. Reusing
    # PasteRequest here made text required -> 422 -> inescapable paste dialog
    # (blocked website-only analysis; Aarvin 2026-07-10).
    property_id: str


@router.post("/runs/{run_id}/paste-content")
async def paste_content(run_id: str, body: PasteRequest, request: Request) -> dict:
    app = request.app
    invoke, labeler = _pipeline_deps(app.state.settings)
    from shiboleth.pipeline.live_run import register_paste, resume_checking

    async with app.state.session_factory() as session:
        await register_paste(session, run_id, body.property_id, body.text)
        await resume_checking(session, invoke, labeler, run_id)
        run = await session.get(Run, run_id)
        return {"run_id": run_id, "status": run.status}


@router.post("/runs/{run_id}/skip-property")
async def skip_property(run_id: str, body: SkipRequest, request: Request) -> dict:
    app = request.app
    invoke, labeler = _pipeline_deps(app.state.settings)
    from shiboleth.pipeline.live_run import register_skip, resume_checking

    async with app.state.session_factory() as session:
        await register_skip(session, run_id, body.property_id)
        await resume_checking(session, invoke, labeler, run_id)
        run = await session.get(Run, run_id)
        return {"run_id": run_id, "status": run.status}


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
