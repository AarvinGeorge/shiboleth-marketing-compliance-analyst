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
            restarts, matching the 07 §2 pause/resume doctrine). Demo
            hardening (2026-07-13): POST /checks is per-IP rate limited
            (CHECKS_RATE_LIMIT_PER_HOUR, 429), the live page cap is clamped
            to PAGE_CAP_MAX, and DELETE /runs refuses PROTECTED_RUN_IDS (403).
  deps: db models, corpus_run, sse-starlette, adlign.api.hardening.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from adlign.api.hardening import RateLimiter, client_key, effective_page_cap
from adlign.db.models import Event, Run

router = APIRouter()


def _rate_limiter(app) -> RateLimiter:
    """One limiter per app instance, built lazily from settings (demo
    hardening; limit 0 in dev keeps it a no-op)."""
    limiter = getattr(app.state, "checks_rate_limiter", None)
    if limiter is None:
        limiter = RateLimiter(
            limit=app.state.settings.checks_rate_limit_per_hour,
            window_seconds=3600,
        )
        app.state.checks_rate_limiter = limiter
    return limiter


class CheckRequest(BaseModel):
    product_id: str
    mode: str = "corpus"
    page_cap: int = 20  # per marketing medium (semantic discovery top-N)


def _pipeline_deps(settings):
    from adlign.evals.harnesses.e3 import PacedCachedInvoke
    from adlign.pipeline.nodes.cluster import groq_labeler

    return (PacedCachedInvoke(settings.model_for("check")),
            groq_labeler(settings.model_for("cluster_label")))


async def _auto_group(app, run_id: str) -> None:
    """grouping-as-a-view: runs arrive pre-grouped; NEVER fails the run."""
    try:
        from adlign.pipeline.nodes.issues import (production_adjudicator,
                                                     production_signer)
        from adlign.services.issues import suggest_issues_for_run

        model = app.state.settings.model_for("issue")
        async with app.state.session_factory() as session:
            await suggest_issues_for_run(
                session, run_id,
                production_signer(model), production_adjudicator(model))
    except Exception as exc:  # noqa: BLE001 — non-fatal by contract
        print(f"issue auto-suggest skipped: {type(exc).__name__}: {exc}")


async def _verify_if_enabled(app, run_id: str) -> None:
    """Trust Stage 2: run the independent verifier over the run's flags when
    ENABLE_VERIFIER is on. Advisory + non-blocking: NEVER fails the run, and
    per-flag failures inside verify_run_flags leave flags unverified."""
    settings = app.state.settings
    if not settings.enable_verifier:
        return
    try:
        from adlign.pipeline.nodes.verify import production_verify_invoke
        from adlign.services.verification import verify_run_flags

        model_string = settings.model_for("verify")
        async with app.state.session_factory() as session:
            await verify_run_flags(
                session, run_id, production_verify_invoke(model_string), model_string)
    except Exception as exc:  # noqa: BLE001 — advisory, never fatal
        print(f"verifier pass skipped: {type(exc).__name__}: {exc}")


async def _guarded(app, coro, run_id: str | None = None) -> None:
    """Fail LOUD, never silent (2026-07-14; trace analysis found provider
    hard failures — spend-cap 400s, 429s — killing the background task and
    leaving the run row "running" forever, a zombie lane in the sidebar).
    An unhandled failure marks the run failed and appends an "error" event
    — the SSE stream's existing terminate type, so open streams end."""
    try:
        await coro
    except Exception as exc:  # noqa: BLE001 — background task, no caller to raise to
        print(f"run task failed: {type(exc).__name__}: {exc}")
        if run_id is None:
            return
        async with app.state.session_factory() as session:
            run = await session.get(Run, run_id)
            if run is not None and run.status not in ("completed", "failed"):
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                session.add(Event(
                    run_id=run_id, node="graph", event_type="error",
                    payload={"error": f"{type(exc).__name__}: {exc}"[:300]},
                    ts=datetime.now(UTC),
                ))
                await session.commit()


def _track(app, coro, run_id: str | None = None) -> None:
    run_task = asyncio.create_task(_guarded(app, coro, run_id))
    app.state.live_tasks = getattr(app.state, "live_tasks", set())
    app.state.live_tasks.add(run_task)
    run_task.add_done_callback(app.state.live_tasks.discard)


@router.post("/checks")
async def start_check(body: CheckRequest, request: Request) -> dict:
    """BOTH modes are background tasks (2026-07-13: a corpus re-run after a
    harness change refills the LLM cache — minutes of live calls — and a
    synchronous request made the UI look broken while the server quietly
    finished). The caller gets {run_id, status: started} immediately and
    watches progress via the run events."""
    app = request.app
    if not _rate_limiter(app).allow(client_key(request)):
        raise HTTPException(
            status_code=429,
            detail="Rate limited: too many check runs from this address; "
                   "try again in an hour.")
    invoke, labeler = _pipeline_deps(app.state.settings)

    if body.mode == "corpus":
        from adlign.pipeline.corpus_run import run_corpus

        async def corpus_task():
            async with app.state.session_factory() as session:
                run_id = await run_corpus(session, invoke, labeler,
                                          product_id=body.product_id)
            await _auto_group(app, run_id)
            await _verify_if_enabled(app, run_id)

        _track(app, corpus_task())
        return {"status": "started", "mode": "corpus"}

    # live: run row created + committed HERE so the caller gets its id
    # immediately; one async task owns ingest (semantic discovery when the
    # site has a sitemap) -> checking -> clusters -> auto-grouping. Mediums
    # are optional; failures auto-skip; no awaiting_input barrier.
    from adlign.pipeline.live_run import create_live_run, start_live_run
    from adlign.services.ingestion.discovery import production_ranker

    async with app.state.session_factory() as session:
        run_id = await create_live_run(session, body.product_id)
    ranker = production_ranker(app.state.settings.model_for("discover"))

    cap = effective_page_cap(body.page_cap, app.state.settings)

    async def live_task():
        async with app.state.session_factory() as session:
            await start_live_run(session, invoke, labeler,
                                 product_id=body.product_id, run_id=run_id,
                                 cap=cap, ranker=ranker)
        await _auto_group(app, run_id)
        await _verify_if_enabled(app, run_id)

    _track(app, live_task(), run_id=run_id)
    return {"run_id": run_id, "status": "started"}


class PasteRequest(BaseModel):
    property_id: str
    text: str


class SkipRequest(BaseModel):
    # skip carries no content: the UI sends {property_id} only. Reusing
    # PasteRequest here made text required -> 422 -> inescapable paste dialog
    # (blocked website-only analysis; Aarvin 2026-07-10).
    property_id: str


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str, request: Request) -> dict:
    """Delete a check run and ALL its records: events, flags, clusters,
    inventory, then the run row. Shared page snapshots (materials) are
    content-addressed and shared across runs, so they survive — deleting
    one run must never orphan another run's evidence. Runs listed in
    PROTECTED_RUN_IDS (the seeded showcase data on the public demo) are
    refused before any DB work."""
    if run_id in request.app.state.settings.protected_run_ids:
        raise HTTPException(
            status_code=403,
            detail=f"run {run_id} is protected demo data and cannot be deleted")
    from sqlalchemy import delete as sql_delete

    from adlign.db.models import Cluster, Event, Flag, Run, RunInventory

    async with request.app.state.session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        await session.execute(sql_delete(Event).where(Event.run_id == run_id))
        await session.execute(sql_delete(Flag).where(Flag.run_id == run_id))
        await session.execute(sql_delete(Cluster).where(Cluster.run_id == run_id))
        await session.execute(
            sql_delete(RunInventory).where(RunInventory.run_id == run_id))
        await session.delete(run)
        await session.commit()
    return {"deleted": run_id}


class IssueStateRequest(BaseModel):
    state: str  # confirmed | rejected


@router.post("/runs/{run_id}/issue-suggestions")
async def suggest_issues(run_id: str, request: Request) -> list[dict]:
    """Generate SUGGESTED issue groupings over this run's wording clusters
    (clustering C1). Idempotent: already-parented clusters and rejected
    snapshots are skipped, so re-calling never duplicates or re-suggests."""
    from adlign.pipeline.nodes.issues import (production_adjudicator,
                                                 production_signer)
    from adlign.services.issues import suggest_issues_for_run

    settings = request.app.state.settings
    model = settings.model_for("issue")
    async with request.app.state.session_factory() as session:
        return await suggest_issues_for_run(
            session, run_id,
            production_signer(model), production_adjudicator(model))


@router.patch("/clusters/{cluster_id}/issue-state")
async def issue_state(cluster_id: str, body: IssueStateRequest,
                      request: Request) -> dict:
    """Analyst confirm/reject of a suggested issue grouping. Reject detaches
    the wording clusters and remembers the grouping so it is never
    re-suggested."""
    from fastapi import HTTPException

    from adlign.services.issues import set_issue_state

    async with request.app.state.session_factory() as session:
        try:
            return await set_issue_state(session, cluster_id, body.state)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/paste-content")
async def paste_content(run_id: str, body: PasteRequest, request: Request) -> dict:
    app = request.app
    invoke, labeler = _pipeline_deps(app.state.settings)
    from adlign.pipeline.live_run import register_paste, resume_checking

    async with app.state.session_factory() as session:
        await register_paste(session, run_id, body.property_id, body.text)
        await resume_checking(session, invoke, labeler, run_id)
        run = await session.get(Run, run_id)
        return {"run_id": run_id, "status": run.status}


@router.post("/runs/{run_id}/skip-property")
async def skip_property(run_id: str, body: SkipRequest, request: Request) -> dict:
    app = request.app
    invoke, labeler = _pipeline_deps(app.state.settings)
    from adlign.pipeline.live_run import register_skip, resume_checking

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
