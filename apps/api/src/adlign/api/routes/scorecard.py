"""
meta:
  purpose: Scorecard routes (customize layer): read the scorecard, add a
           rule (auto-decomposed + keyword-derived), edit/delete rules and
           their binary checks. Live runs pick the edited scorecard up
           automatically (DB-driven); corpus runs stay on the frozen seeded
           benchmark.
  contract: DELETE returns 409 when flags reference the rule/check (audit
            rows are never orphaned). Rule verbatim_text is stored exactly
            as entered.
  deps: services.scorecard, pipeline.nodes.decompose.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from adlign.services.scorecard import (Conflict, create_rule,
                                          delete_check, delete_rule,
                                          get_scorecard, update_rule,
                                          upsert_check)

router = APIRouter()


class RuleCreate(BaseModel):
    verbatim_text: str
    severity: str = "Medium"


class RuleUpdate(BaseModel):
    verbatim_text: str | None = None
    severity: str | None = None
    regenerate: bool = False


class CheckUpsert(BaseModel):
    kind: str = "requirement"  # trigger | requirement
    text: str
    evidence_criteria: str = ""


def _decomposer(request: Request):
    from adlign.pipeline.nodes.decompose import production_decomposer
    return production_decomposer(
        request.app.state.settings.model_for("decompose"))


@router.get("/scorecard")
async def read_scorecard(request: Request) -> list[dict]:
    async with request.app.state.session_factory() as session:
        return await get_scorecard(session)


@router.post("/scorecard/rules")
async def add_rule(body: RuleCreate, request: Request) -> dict:
    if not body.verbatim_text.strip():
        raise HTTPException(status_code=422, detail="rule text is required")
    async with request.app.state.session_factory() as session:
        return await create_rule(session, body.verbatim_text,
                                 body.severity, _decomposer(request))


@router.patch("/scorecard/rules/{rule_id}")
async def edit_rule(rule_id: str, body: RuleUpdate, request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        try:
            return await update_rule(
                session, rule_id, body.verbatim_text, body.severity,
                body.regenerate,
                _decomposer(request) if body.regenerate else None)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/scorecard/rules/{rule_id}")
async def remove_rule(rule_id: str, request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        try:
            await delete_rule(session, rule_id)
        except Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": rule_id}


@router.post("/scorecard/rules/{rule_id}/checks")
async def add_check(rule_id: str, body: CheckUpsert, request: Request) -> dict:
    if body.kind not in ("trigger", "requirement"):
        raise HTTPException(status_code=422, detail="kind must be trigger or requirement")
    async with request.app.state.session_factory() as session:
        return await upsert_check(session, rule_id, None, body.kind,
                                  body.text, body.evidence_criteria)


@router.patch("/scorecard/checks/{check_id}")
async def edit_check(check_id: str, body: CheckUpsert, request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        try:
            return await upsert_check(session, "", check_id, body.kind,
                                      body.text, body.evidence_criteria)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/scorecard/checks/{check_id}")
async def remove_check(check_id: str, request: Request) -> dict:
    async with request.app.state.session_factory() as session:
        try:
            await delete_check(session, check_id)
        except Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": check_id}
