"""
meta:
  purpose: Disposition endpoint (S3 choreography, 07 §3): validate lifecycle
           transition, update flag, append eval_items (dismissed = FP label),
           recompute verified scores (pure SQL/Python, no LLM), return
           {flag, scores} so the UI updates without SSE. Plus the per-flag
           severity override (2026-07-14): PATCH /flags/{id}/severity.
  contract: POST /flags/{id}/disposition {action: confirm|dismiss, team?,
            note?}. confirm+team -> assigned (confirm then assign, one call —
            the U6/U7 Disposition panel's shape). Illegal transition -> 409.
            PATCH /flags/{id}/severity {severity: High|Medium|Low|null};
            null resets to the rule's recommendation. Effective severity =
            override ?? rule severity; persisted outcome_rows are NEVER
            rewritten (audit trail) — overrides affect display and metrics
            only. Every change appends an events row (severity_overridden,
            payload {from, to} effective values).
  deps: db models, scoring metrics glue, formulas.validate_transition.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from adlign.db.models import BinaryCheck, EvalItem, Event, Flag, Rule, Run
from adlign.domain.schemas import Disposition
from adlign.services.scoring.formulas import InvalidTransition, validate_transition
from adlign.services.scoring.metrics import outcomes_to_scores

router = APIRouter()

SEVERITY_BY_RULE = {"R-01": "High", "R-02": "High", "R-03": "Medium", "R-04": "Medium"}

SEVERITIES = ("High", "Medium", "Low")


def _severity(check_id: str) -> str:
    return SEVERITY_BY_RULE.get(check_id.rsplit("-", 1)[0], "Medium")


class SeverityOverride(BaseModel):
    severity: str | None = None  # High | Medium | Low | null (= reset)


@router.patch("/flags/{flag_id}/severity")
async def override_severity(flag_id: str, body: SeverityOverride,
                            request: Request) -> dict:
    """Human-editable severity (Aarvin overruled the deferral, 2026-07-14).
    NULL resets to the rule's recommendation. Audit: events row per change;
    outcome_rows untouched."""
    if body.severity is not None and body.severity not in SEVERITIES:
        raise HTTPException(422, "severity must be High, Medium, Low or null")
    async with request.app.state.session_factory() as session:
        flag = await session.get(Flag, flag_id)
        if flag is None:
            raise HTTPException(404, "flag not found")
        from adlign.services.scoring.formulas import recommended_severity

        rule_severity = (await session.execute(
            select(Rule.severity)
            .join(BinaryCheck, BinaryCheck.rule_id == Rule.id)
            .where(BinaryCheck.id == flag.check_id)
        )).scalar_one_or_none() or _severity(flag.check_id)
        # matrix-aware (2026-07-14): a null reset lands on the matrix
        # recommendation, not the bare rule severity
        recommended = recommended_severity(rule_severity, flag.intersection_tag)
        previous_effective = flag.severity_override or recommended
        flag.severity_override = body.severity
        effective = body.severity or recommended
        session.add(Event(
            run_id=flag.run_id, flag_id=flag.id, node="severity",
            event_type="severity_overridden",
            payload={"from": previous_effective, "to": effective},
            ts=datetime.now(UTC),
        ))
        await session.commit()
        return {
            "id": flag.id,
            "severity_override": flag.severity_override,
            "severity_effective": effective,
            "severity_recommended": recommended,
            "severity_overridden": flag.severity_override is not None,
        }


@router.post("/flags/{flag_id}/disposition")
async def disposition(flag_id: str, body: Disposition, request: Request) -> dict:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        flag = await session.get(Flag, flag_id)
        if flag is None:
            raise HTTPException(404, "flag not found")

        try:
            if body.action == "dismiss":
                validate_transition(flag.state, "dismissed")
                flag.state = "dismissed"
            else:  # confirm (+ optional team -> assigned in the same call)
                validate_transition(flag.state, "confirmed")
                flag.state = "confirmed"
                if body.team:
                    validate_transition(flag.state, "assigned")
                    flag.state = "assigned"
                    flag.assigned_team = body.team
        except InvalidTransition as exc:
            raise HTTPException(409, str(exc)) from exc

        flag.note = body.note
        flag.dispositioned_at = datetime.now(UTC)

        session.add(EvalItem(
            harness="checker", source="disposition",
            input={"flag_id": flag.id, "check_id": flag.check_id,
                   "evidence_quote": flag.evidence_quote},
            expected={"disposition": body.action, "note": body.note},
        ))

        # verified recompute: replay the SAME formula over the SAME outcome
        # rows the run persisted (corpus_run stores them in runs.scores)
        run = await session.get(Run, flag.run_id)
        flags = (await session.execute(
            select(Flag).where(Flag.run_id == run.id)
        )).scalars().all()
        dismissed = {f.id for f in flags if f.state == "dismissed"}
        outcome_rows = (run.scores or {}).get("outcome_rows", [])
        recomputed = outcomes_to_scores(outcome_rows, dismissed_ids=dismissed)
        run.scores = {**(run.scores or {}), "verified": recomputed["verified"],
                      "per_property": recomputed["per_property"]}
        await session.commit()

        return {
            "flag": {"id": flag.id, "state": flag.state,
                     "assigned_team": flag.assigned_team, "note": flag.note},
            "scores": {"draft": (run.scores or {}).get("draft"),
                       "verified": recomputed["verified"],
                       "per_property": recomputed["per_property"]},
        }
