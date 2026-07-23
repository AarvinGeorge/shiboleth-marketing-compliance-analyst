"""
meta:
  purpose: Live-mode run orchestration (07 §2 pinned + §3 S1/S2): N2 ingest
           per property (website via crawl4ai BFS; social parks as
           needs_input — paste fallback is the first-class Meta path), the
           ingest BARRIER (any needs_input ends the graph run; state lives in
           Postgres; resume reconstructs from the DB), then the same checking
           machinery corpus mode certified: shared-block dedup, windowed
           retrieval, N4/N5 checker, N6 clusters, N7 scores, events.
  contract: start_live_run creates the run + ingests + either completes
            checking or parks awaiting_input. register_paste/skip update a
            property; when none remain needs_input, resume_checking finishes
            the run. Coverage (E1-light) written to runs.scores['coverage'].
  deps: live.py (plan/ingest/barrier), crawler.py (crawl4ai), corpus_run
        persistence pieces, e3 windows/checker machinery.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adlign.db.models import Flag, Material, Property, Rule, Run, RunInventory, new_id
from adlign.pipeline.corpus_run import _emit
from adlign.pipeline.nodes.check import run_check
from adlign.pipeline.nodes.cluster import cluster_flags
from adlign.services.ingestion.live import barrier_state
from adlign.services.ingestion.windows import (
    detect_shared_block,
    extract_windows,
    library_anchor_keywords,
    page_has_shared_block,
    strip_shared,
)
from adlign.services.scoring.formulas import content_hash
from adlign.services.scoring.metrics import outcomes_to_scores



async def create_live_run(session: AsyncSession, product_id: str) -> str:
    """Create + COMMIT the run row synchronously so the API can return the id
    before ingest starts (the ingest task then owns the run's lifecycle)."""
    # snapshot the ACTUAL scorecard this run will check against (customize
    # layer: live runs are DB-driven, so the audit trail must record which
    # rules, at what severity, were in force)
    rules = (await session.execute(
        select(Rule).order_by(Rule.position))).scalars().all()
    run = Run(id=new_id(), product_id=product_id, mode="live", status="running",
              started_at=datetime.now(UTC),
              scorecard_snapshot={
                  "scorecard_id": rules[0].scorecard_id if rules else "SC-01",
                  "rules": [{"id": r.id, "severity": r.severity,
                             "verbatim_text": r.verbatim_text} for r in rules],
              },
              scores={})
    session.add(run)
    await session.flush()  # run row must exist before its first event (FK)
    await _emit(session, run.id, "run_started", "graph", {"mode": "live"})
    await session.commit()
    return run.id


async def start_live_run(
    session: AsyncSession, invoke, labeler, product_id: str,
    depth: int = 2, cap: int = 20, run_id: str | None = None,
    ranker=None,
) -> str:
    """Ingestion redesign (Aarvin 2026-07-13): marketing mediums are
    OPTIONAL — whichever fetch succeeds feeds the check; a medium that
    fails is auto-skipped (recorded in coverage) and the run continues.
    No awaiting_input barrier, no modal. Website mediums use SEMANTIC
    discovery when a ranker is provided (sitemap harvest + LLM
    rule-relevance ranking against the LIVE scorecard, top page-cap pages;
    the ground-truth-v2 mechanism) with BFS crawl as the no-sitemap
    fallback. page cap applies PER MEDIUM."""
    if run_id is None:
        run_id = await create_live_run(session, product_id)
    run = await session.get(Run, run_id)
    run.model_config_json = {"check": getattr(invoke, "model_string", "unknown")}

    properties = (await session.execute(
        select(Property).where(Property.product_id == product_id)
    )).scalars().all()

    statuses: dict[str, str] = {}
    for prop in properties:
        await _emit(session, run.id, "node_started", "ingest", {}, )
        try:
            if prop.kind == "website":
                from adlign.services.ingestion.crawler import (crawl_website,
                                                                  fetch_urls)

                pages: list[tuple[str, str]] = []
                if ranker is not None:
                    from adlign.services.ingestion.discovery import discover_urls
                    from adlign.services.scorecard import load_rule_bundles

                    bundles = await load_rule_bundles(session)
                    rules = [b["rule"] for b in bundles]
                    urls = await discover_urls(prop.url_or_handle, rules,
                                               cap, ranker)
                    if urls:
                        await _emit(session, run.id, "pages_discovered",
                                    "ingest", {"mode": "semantic",
                                               "candidates": len(urls)})
                        pages = await fetch_urls(urls)
                if not pages:  # no ranker or no sitemap: BFS fallback
                    pages = await crawl_website(prop.url_or_handle,
                                                depth=depth, cap=cap)
                for url, markdown in pages:
                    await _store_material(session, run, prop.id, url, markdown)
                statuses[prop.id] = "fetched"
                await _emit(session, run.id, "property_status", "ingest",
                            {"status": "fetched", "pages": len(pages)})
            else:
                # social mediums: hard time-boxed attempt is day-2; today the
                # honest behavior is auto-skip (Meta blocks scrapers) — the
                # run NEVER parks on it, coverage records the gap, and paste
                # remains available from the run view
                statuses[prop.id] = "skipped"
                await _emit(session, run.id, "property_status", "ingest",
                            {"status": "skipped",
                             "detail": f"{prop.kind}: automated fetch "
                                       "unavailable; medium skipped"})
        except Exception as exc:  # noqa: BLE001 — a failed medium never blocks the run
            statuses[prop.id] = "skipped"
            await _emit(session, run.id, "property_status", "ingest",
                        {"status": "skipped", "detail": str(exc)[:200]})

    run.scores = {**(run.scores or {}), "property_status": statuses,
                  "config": {"cap_per_medium": cap}}
    await resume_checking(session, invoke, labeler, run.id)
    return run.id


async def _store_material(
    session: AsyncSession, run: Run, property_id: str, ref: str, text: str
) -> None:
    digest = content_hash(text)
    existing = (await session.execute(
        select(Material).where(Material.content_hash == digest)
    )).scalar_one_or_none()
    if existing is None:
        session.add(Material(id=new_id(), property_id=property_id, ref=ref,
                             kind="page", content_hash=digest,
                             extracted_text=text, raw={"run_id": run.id}))
        cache_hit = False
    else:
        cache_hit = True
    session.add(RunInventory(run_id=run.id, ref=ref, content_hash=digest))
    await _emit(session, run.id, "material_fetched", "ingest",
                {"ref": ref, "cache_hit": cache_hit})


async def register_paste(
    session: AsyncSession, run_id: str, property_id: str, text: str
) -> None:
    run = await session.get(Run, run_id)
    await _store_material(session, run, property_id, f"paste://{property_id}", text)
    statuses = dict(run.scores.get("property_status", {}))
    statuses[property_id] = "fetched"
    run.scores = {**run.scores, "property_status": statuses}
    await session.commit()


async def register_skip(session: AsyncSession, run_id: str, property_id: str) -> None:
    run = await session.get(Run, run_id)
    statuses = dict(run.scores.get("property_status", {}))
    statuses[property_id] = "skipped"
    run.scores = {**run.scores, "property_status": statuses}
    await _emit(session, run.id, "property_status", "ingest", {"status": "skipped"})
    await session.commit()


async def resume_checking(session: AsyncSession, invoke, labeler, run_id: str) -> None:
    """The post-barrier half: reconstructs state from the DB (07 §2: run_id is
    the thread id, the DB is the checkpoint) and runs checks -> clusters ->
    scores -> events. Same machinery the corpus certification proved."""
    run = await session.get(Run, run_id)
    statuses = run.scores.get("property_status", {})
    if barrier_state(statuses) == "awaiting_input":
        return  # properties still parked; caller re-invokes after paste/skip
    run.status = "running"
    await _emit(session, run.id, "run_resumed", "graph", {})

    inventory = (await session.execute(
        select(RunInventory).where(RunInventory.run_id == run_id)
    )).scalars().all()
    hashes = [row.content_hash for row in inventory]
    materials = (await session.execute(
        select(Material).where(Material.content_hash.in_(hashes))
    )).scalars().all() if hashes else []

    bodies = [m.extracted_text for m in materials]
    # live shared-block dedup scales to the crawl size (corpus used 20/54)
    min_pages = max(3, len(bodies) // 2 + 1)
    shared = detect_shared_block(bodies, min_pages=min_pages) if len(bodies) >= 3 else []
    shared_text = "\n\n".join(shared)

    # customize layer (2026-07-13): LIVE runs are DB-driven — user-added and
    # edited rules apply here. Corpus runs stay on the frozen seeded
    # constants (certification benchmark). Keyword families: DB-derived for
    # user rules, windows.py registry for seeded ones.
    from adlign.services.scorecard import load_rule_bundles

    bundles = await load_rule_bundles(session)
    severity_by_rule = {b["rule"]["id"]: b["rule"]["severity"] for b in bundles}

    flag_rows, score_rows = [], []
    footer_outcomes = {}
    if shared:
        for b in bundles:
            rule_id, rule, checks, library = (b["rule"]["id"], b["rule"],
                                              b["checks"], b["library"])
            anchors = library_anchor_keywords(library["approved_text"]) if library else None
            windows = extract_windows(shared_text, rule_id, max_total_chars=12_000,
                                      extra_keywords=anchors,
                                      keywords=b["keywords"])
            if windows:
                footer_outcomes[rule_id] = run_check(
                    "\n\n".join(windows), rule, checks, library, invoke)

    for material in materials:
        body = strip_shared(material.extracted_text, shared) if shared \
            else material.extracted_text
        carries_shared = shared and page_has_shared_block(material.extracted_text, shared)
        for b in bundles:
            rule_id, rule, checks, library = (b["rule"]["id"], b["rule"],
                                              b["checks"], b["library"])
            anchors = library_anchor_keywords(library["approved_text"]) if library else None
            windows = extract_windows(body, rule_id, extra_keywords=anchors,
                                      fallback_chars=24_000,
                                      keywords=b["keywords"])
            outcomes_here = []
            if windows:
                outcomes_here.append(("page", run_check(
                    "\n\n".join(windows), rule, checks, library, invoke)))
            if carries_shared and rule_id in footer_outcomes:
                outcomes_here.append(("shared", footer_outcomes[rule_id]))
            if not outcomes_here:
                score_rows.append({"verdict_status": "not_applicable",
                                   "severity": severity_by_rule[rule_id],
                                   "property_id": material.property_id,
                                   "flag_id": None})
                continue
            for scope, outcome in outcomes_here:
                status = outcome.verdict_status
                row = {"verdict_status": status, "severity": severity_by_rule[rule_id],
                       "property_id": material.property_id, "flag_id": None}
                score_rows.append(row)
                if status in ("flag", "needs_review"):
                    flag = Flag(id=new_id(), run_id=run.id, material_id=material.id,
                                check_id=f"{rule_id}-REQ", axis_a=bool(outcome.axis_a),
                                axis_b=outcome.axis_b,
                                intersection_tag=outcome.intersection_tag or "na",
                                evidence_quote=outcome.evidence_quote,
                                location=f"{material.ref} ({scope})",
                                reason=outcome.reason, confidence=outcome.confidence,
                                state="open")
                    session.add(flag)
                    flag_rows.append(flag)
                    row["flag_id"] = flag.id
    # flags MUST flush before their events (FK; same pattern as corpus_run —
    # the ORM's insert ordering does not respect this dependency reliably)
    await session.flush()
    for flag in flag_rows:
        await _emit(session, run.id, "check_result", "check",
                    {"verdict": "flag" if flag.axis_a is False or flag.axis_b is False
                     else "needs_review", "tag": flag.intersection_tag},
                    flag_id=flag.id)

    clusters = cluster_flags(
        [{"id": f.id, "check_id": f.check_id, "evidence_quote": f.evidence_quote}
         for f in flag_rows], labeler)
    from adlign.db.models import Cluster
    for c in clusters:
        row = Cluster(id=new_id(), run_id=run.id, label=c["label"], kind="wording")
        session.add(row)
        for f in flag_rows:
            if f.id in set(c["member_flag_ids"]):
                f.cluster_id = row.id
    await _emit(session, run.id, "node_finished", "cluster", {"clusters": len(clusters)})

    scores = outcomes_to_scores(score_rows, dismissed_ids=set())
    coverage = {  # E1-light (08 §4): coverage counts vs run inventory
        "pages_fetched": len(inventory),
        "cap": run.scores.get("config", {}).get("cap"),
        "materials_checked": len(materials),
        "properties": statuses,
    }
    run.scores = {**run.scores, **scores, "outcome_rows": score_rows,
                  "coverage": coverage}
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    await _emit(session, run.id, "scores_updated", "score", scores)
    await _emit(session, run.id, "run_finished", "graph", {"status": "completed"})
    await session.commit()
