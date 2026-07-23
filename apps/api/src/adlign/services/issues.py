"""
meta:
  purpose: DB orchestration for the issue-cluster layer (clustering C1):
           generate SUGGESTED issue parents over a run's wording clusters,
           and apply the analyst's confirm/reject decision.
  contract: suggest_issues_for_run(session, run_id, signer, adjudicator)
            -> [issue payloads]; idempotent-ish (already-parented wording
            clusters and rejected snapshots are skipped, so re-calling never
            duplicates or re-suggests refused groupings).
            set_issue_state(session, cluster_id, "confirmed"|"rejected");
            reject detaches children but KEEPS the parent row as the
            never-again memory (member_snapshot). Events persisted per 07 §6.
  deps: db models, pipeline.nodes.issues.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adlign.db.models import Cluster, Event, Flag
from adlign.pipeline.nodes.issues import suggest_issue_groups


def _rule_of(check_id: str) -> str:
    return check_id.rsplit("-", 1)[0]  # "R-01-REQ" -> "R-01"


async def suggest_issues_for_run(
    session: AsyncSession, run_id: str, signer, adjudicator,
) -> list[dict]:
    wording = (await session.execute(
        select(Cluster).where(Cluster.run_id == run_id,
                              Cluster.kind == "wording",
                              Cluster.parent_cluster_id.is_(None))
    )).scalars().all()
    issues = (await session.execute(
        select(Cluster).where(Cluster.run_id == run_id,
                              Cluster.kind == "issue")
    )).scalars().all()
    rejected = [set(c.member_snapshot.get("member_cluster_ids", []))
                for c in issues if c.state == "rejected"]

    candidates = []
    for c in wording:
        flag = (await session.execute(
            select(Flag).where(Flag.cluster_id == c.id).limit(1)
        )).scalars().first()
        if flag is None:
            continue
        candidates.append({
            "id": c.id, "rule_id": _rule_of(flag.check_id),
            "label": c.label, "sample_quote": flag.evidence_quote,
        })

    suggestions = suggest_issue_groups(candidates, signer, adjudicator,
                                       rejected_snapshots=rejected)
    payloads = []
    for s in suggestions:
        parent = Cluster(
            run_id=run_id, label=s["label"], kind="issue",
            state="suggested", rationale=s["rationale"],
            member_snapshot={"member_cluster_ids": s["member_cluster_ids"],
                             "signatures": s["signatures"]},
        )
        session.add(parent)
        await session.flush()
        for cid in s["member_cluster_ids"]:
            child = next(c for c in wording if c.id == cid)
            child.parent_cluster_id = parent.id
        session.add(Event(
            run_id=run_id, event_type="issue_suggested", node="issues",
            payload={"cluster_id": parent.id, "label": parent.label,
                     "members": s["member_cluster_ids"],
                     "rationale": parent.rationale},
            ts=datetime.now(UTC),
        ))
        payloads.append({
            "id": parent.id, "label": parent.label, "state": parent.state,
            "rationale": parent.rationale,
            "member_cluster_ids": s["member_cluster_ids"],
            "signatures": s["signatures"],
        })
    await session.commit()
    return payloads


async def set_issue_state(
    session: AsyncSession, cluster_id: str, state: str,
) -> dict:
    """confirmed: keep grouping. rejected: UNGROUP (detach children; parent
    kept as memory). suggested: UNDO an ungroup — re-attach the snapshot
    members that are still unparented (grouping-as-a-view redesign,
    2026-07-13: every action must be reversible in place)."""
    if state not in ("confirmed", "rejected", "suggested"):
        raise ValueError("state must be confirmed, rejected or suggested")
    parent = (await session.execute(
        select(Cluster).where(Cluster.id == cluster_id,
                              Cluster.kind == "issue")
    )).scalars().first()
    if parent is None:
        raise LookupError(f"issue cluster {cluster_id} not found")
    parent.state = state
    if state == "rejected":
        children = (await session.execute(
            select(Cluster).where(Cluster.parent_cluster_id == parent.id)
        )).scalars().all()
        for child in children:
            child.parent_cluster_id = None
    elif state == "suggested":
        member_ids = parent.member_snapshot.get("member_cluster_ids", [])
        members = (await session.execute(
            select(Cluster).where(Cluster.id.in_(member_ids))
        )).scalars().all()
        for m in members:
            if m.parent_cluster_id is None:
                m.parent_cluster_id = parent.id
    session.add(Event(
        run_id=parent.run_id, event_type=f"issue_{state}", node="issues",
        payload={"cluster_id": parent.id, "label": parent.label},
        ts=datetime.now(UTC),
    ))
    await session.commit()
    return {"id": parent.id, "state": parent.state}
