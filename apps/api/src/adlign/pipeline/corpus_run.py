"""
meta:
  purpose: Corpus-mode run persistence (08 §2: corpus is a FIRST-CLASS run
           mode). Executes the production checker path (windows + footer
           inheritance + N4/N5) over the frozen snapshots and persists a full
           run to Postgres: run row, materials (hash-bound), PER-PAGE flags
           (footer inheritance materializes one flag per carrying page —
           binding condition), clusters (N6), scores (N7), events (07 §6:
           rows first, SSE later at M4).
  contract: run_corpus(session, invoke, product_id) -> run_id. Reuses the E3
            harness's corpus_outcomes so eval and persistence NEVER diverge.
  deps: db models, e3.corpus_outcomes, cluster.cluster_flags,
        metrics.outcomes_to_scores, formulas severity lookup via seed RULES.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from adlign.db.models import Cluster, Event, Flag, Material, Run, new_id
from adlign.db.seed import PRODUCT_ID, RULES
from adlign.evals.harnesses.e3 import GROUND_TRUTH_DIR, corpus_outcomes
from adlign.pipeline.nodes.cluster import cluster_flags
from adlign.services.ingestion.corpus import load_corpus
from adlign.services.scoring.metrics import outcomes_to_scores

SEVERITY = {rule_id: severity for rule_id, _t, severity, _p in RULES}


async def _emit(session: AsyncSession, run_id: str, event_type: str, node: str,
                payload: dict, flag_id: str | None = None) -> None:
    session.add(Event(run_id=run_id, flag_id=flag_id, node=node,
                      event_type=event_type, payload=payload))


async def run_corpus(session: AsyncSession, invoke, labeler,
                     product_id: str = PRODUCT_ID) -> str:
    run = Run(product_id=product_id, mode="corpus", status="running",
              started_at=datetime.now(UTC),
              scorecard_snapshot={"scorecard_id": "SC-01", "rules": len(RULES)},
              # audit trail must attribute the actual checker model (Aarvin
              # caught the UI showing a stale policy default)
              model_config_json={"check": getattr(invoke, "model_string", "unknown")})
    session.add(run)
    await session.flush()
    await _emit(session, run.id, "run_started", "graph", {"mode": "corpus"})

    # materials: content-addressed cache/dedup (04 §6g refinement 1) — reuse
    # the stored material when its hash exists, insert only when new
    from sqlalchemy import select

    snapshots = load_corpus(GROUND_TRUTH_DIR / "snapshots")
    materials: dict[str, Material] = {}
    for doc in snapshots:
        existing = (await session.execute(
            select(Material).where(Material.content_hash == doc.content_hash)
        )).scalar_one_or_none()
        cache_hit = existing is not None
        if existing is None:
            existing = Material(property_id="tt-website", ref=doc.url, kind="page",
                                content_hash=doc.content_hash,
                                extracted_text=doc.body,
                                raw={"page_id": doc.page_id, "source": doc.source})
            session.add(existing)
        materials[doc.page_id] = existing
        await _emit(session, run.id, "material_fetched", "ingest",
                    {"ref": doc.url, "cache_hit": cache_hit, "corpus": True})
    await session.flush()

    outcomes = corpus_outcomes(invoke)  # cache makes this cheap post-E3
    await _emit(session, run.id, "node_finished", "check",
                {"outcomes": len(outcomes)})

    flag_rows, score_rows = [], []
    for (page_id, rule_id, scope), outcome in outcomes.items():
        if scope == "synthetic" or page_id not in materials:
            continue
        status = "not_applicable" if outcome is None else outcome.verdict_status
        score_rows.append({"verdict_status": status, "severity": SEVERITY[rule_id],
                           "property_id": "tt-website", "flag_id": None})
        if outcome is None or status not in ("flag", "needs_review"):
            continue
        # explicit id: the column default fires at flush, and score_rows needs
        # the id NOW for the verified-recompute linkage (Lane B blocker 1)
        flag = Flag(
            id=new_id(),
            run_id=run.id, material_id=materials[page_id].id,
            check_id=f"{rule_id}-REQ", axis_a=bool(outcome.axis_a),
            axis_b=outcome.axis_b, intersection_tag=outcome.intersection_tag or "na",
            evidence_quote=outcome.evidence_quote,
            location=f"{page_id} ({scope})", reason=outcome.reason,
            confidence=outcome.confidence, state="open",
            evidence_valid=outcome.evidence_valid, ambiguous=outcome.ambiguous,
        )
        session.add(flag)
        flag_rows.append(flag)
        score_rows[-1]["flag_id"] = flag.id
    await session.flush()
    for flag in flag_rows:
        await _emit(session, run.id, "check_result", "check",
                    {"verdict": "flag", "tag": flag.intersection_tag},
                    flag_id=flag.id)

    # N6: cluster identical-evidence flags (template propagation)
    clusters = cluster_flags(
        [{"id": f.id, "check_id": f.check_id, "evidence_quote": f.evidence_quote}
         for f in flag_rows],
        labeler,
    )
    for c in clusters:
        row = Cluster(run_id=run.id, label=c["label"], kind="wording")
        session.add(row)
        await session.flush()
        for f in flag_rows:
            if f.id in set(c["member_flag_ids"]):
                f.cluster_id = row.id
    await _emit(session, run.id, "node_finished", "cluster",
                {"clusters": len(clusters)})

    # N7: scores — outcome rows persisted alongside so disposition recompute
    # replays the SAME formula over the SAME rows (no derivation tricks)
    scores = outcomes_to_scores(score_rows, dismissed_ids=set())
    # coverage: corpus is 54 website pages, no social — record it so the
    # dashboard card shows only the channel actually analyzed (parity with
    # live runs, which store fetched/skipped per property)
    coverage = {"properties": {"tt-website": "fetched"},
                "materials_checked": len(materials)}
    run.scores = {**scores, "outcome_rows": score_rows, "coverage": coverage}
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    await _emit(session, run.id, "scores_updated", "score", scores)
    await _emit(session, run.id, "run_finished", "graph", {"status": "completed"})
    await session.commit()
    return run.id
