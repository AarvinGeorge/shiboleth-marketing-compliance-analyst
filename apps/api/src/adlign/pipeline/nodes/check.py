"""
meta:
  purpose: N4 checker + N5 reconciliation core (01_spec §4). Evaluates ONE
           material against ONE rule via its trigger+requirement checks with
           an LLM structured-output call, then derives axes, intersection tag,
           and verdict_status. Evidence is validated programmatically:
           quote must substring-match the material or the verdict degrades to
           needs_review (guardrail 4 — never trust the model on evidence).
  contract: run_check(material_text, rule, checks, library_entry, invoke) ->
            CheckOutcome. `invoke: (prompt) -> CheckerVerdict` is the LLM seam
            (production: structured-output model; tests: cassette wrapper).
            Axis B (N5): library-linked rule -> approved-text comparison;
            unlinked -> na on pass, False on violation (mirrors frozen ground
            truth). Untriggered = N/A, never pass (guardrail).
  deps: pydantic, adlign.services.scoring.formulas (derivation single
        source). No DB access; pure given its inputs + the LLM call.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field

from adlign.services.scoring.formulas import derive_intersection


class CheckerVerdict(BaseModel):
    """Structured output the checker model must return."""
    trigger_met: bool = Field(description="Does the material trigger this rule?")
    requirement_met: bool | None = Field(
        description="If triggered: is the requirement satisfied? null when not triggered."
    )
    evidence_quote: str = Field(
        description="VERBATIM quote from the material supporting the verdict. "
        "Empty string only when the rule is not triggered."
    )
    location: str = Field(description="Where in the material the evidence sits.")
    reason: str = Field(description="Concise analyst reasoning for the verdict.")
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguous: bool = Field(
        default=False,
        description="True ONLY when the verdict is a genuine judgment call the "
        "analyst should review, per the rule's evidence criteria (e.g. the "
        "primary claim carries the disclosure but secondary mentions do not).",
    )


@dataclass(frozen=True)
class CheckOutcome:
    verdict_status: str  # pass | flag | not_applicable | needs_review
    trigger_met: bool
    requirement_met: bool | None
    axis_a: bool | None
    axis_b: bool | None
    intersection_tag: str | None
    approval_na: bool
    evidence_quote: str
    evidence_valid: bool
    location: str
    reason: str
    confidence: float


PROMPT_TEMPLATE = """You are a marketing-compliance analyst for a fintech's bank partner. \
Judge ONE rule against ONE marketing material. Be precise and conservative: \
never invent content that is not in the material.

## The rule (verbatim, canonical)
{rule_text}

## Binary checks
TRIGGER: {trigger_text}
Trigger evidence criteria: {trigger_criteria}

REQUIREMENT (only if triggered): {requirement_text}
Requirement evidence criteria: {requirement_criteria}
{library_block}
## Decision procedure
1. Decide trigger_met from the trigger check only. If the trigger is NOT met, \
requirement_met must be null and evidence_quote must be an empty string.
2. If triggered, decide requirement_met strictly against the requirement check \
and its criteria. Positional requirements (e.g. "right underneath") mean the \
disclosure must be adjacent to the triggering claim, not merely somewhere on \
the page.
3. evidence_quote MUST be ONE SINGLE CONTIGUOUS passage copied \
character-for-character from the material. NEVER stitch together text from \
different lines, paragraphs, or sections; never insert ellipses or bridge \
words. If more than one passage matters, quote only the single most \
probative one and name where the others sit in `location` and `reason`.
4. reason: 1-3 sentences of analyst reasoning. confidence: 0.0-1.0.

## The material (extracted page text)
<material>
{material_text}
</material>"""

LIBRARY_BLOCK = """
## Approved library entry ({library_id})
The pre-approved text for this disclosure is:
"{approved_text}"
"""


def build_prompt(
    material_text: str,
    rule: dict,
    trigger: dict,
    requirement: dict,
    library_entry: dict | None,
) -> str:
    library_block = (
        LIBRARY_BLOCK.format(
            library_id=library_entry["id"], approved_text=library_entry["approved_text"]
        )
        if library_entry
        else ""
    )
    return PROMPT_TEMPLATE.format(
        rule_text=rule["verbatim_text"],
        trigger_text=trigger["text"],
        trigger_criteria=trigger["evidence_criteria"],
        requirement_text=requirement["text"],
        requirement_criteria=requirement["evidence_criteria"],
        library_block=library_block,
        material_text=material_text,
    )


_WS = re.compile(r"\s+")
_MD_EMPHASIS = re.compile(r"[*_`]+")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def _normalize(text: str) -> str:
    """Whitespace-collapse + case-fold + markdown syntax strip: emphasis
    markers (iter-7 postmortem) and link wrappers [text](url) -> text
    (iter-10 postmortem: the P04 disclosure rendered as a link failed the
    axis-B verbatim comparison on markup, not wording). Markdown is
    RENDERING; content characters are never altered — 'Roughly 37%' still
    does not match '~37%'."""
    text = _MD_LINK.sub(r"\1", text)
    return _WS.sub(" ", _MD_EMPHASIS.sub("", text)).strip().lower()


def evidence_in_material(quote: str, material_text: str) -> bool:
    """Whitespace-tolerant substring check (crawl4ai wraps lines; the model
    quotes logical lines). Exact-after-normalization, no fuzz beyond that."""
    if not quote.strip():
        return False
    return _normalize(quote) in _normalize(material_text)


def reconcile_axis_b(
    axis_a: bool,
    requirement_met: bool | None,
    evidence_quote: str,
    library_entry: dict | None,
    material_text: str,
) -> bool | None:
    """N5: axis B (matches pre-approved library material).
    Library-linked rule: approved text present verbatim (normalized) -> True;
    absent or drifted -> False. Unlinked rule: na on pass, False on violation
    (mirrors the frozen ground-truth convention)."""
    if library_entry is None:
        return None if axis_a else False
    approved_present = _normalize(library_entry["approved_text"]) in _normalize(
        material_text
    )
    return approved_present


def run_check(
    material_text: str,
    rule: dict,
    checks: list[dict],
    library_entry: dict | None,
    invoke: Callable[[str], CheckerVerdict],
) -> CheckOutcome:
    trigger = next(c for c in checks if c["kind"] == "trigger")
    requirement = next(c for c in checks if c["kind"] == "requirement")
    prompt = build_prompt(material_text, rule, trigger, requirement, library_entry)
    verdict = invoke(prompt)

    if not verdict.trigger_met:
        return CheckOutcome(
            verdict_status="not_applicable",
            trigger_met=False,
            requirement_met=None,
            axis_a=None,
            axis_b=None,
            intersection_tag=None,
            approval_na=True,
            evidence_quote="",
            evidence_valid=True,  # nothing to validate on N/A
            location=verdict.location,
            reason=verdict.reason,
            confidence=verdict.confidence,
        )

    requirement_met = bool(verdict.requirement_met)
    axis_a = requirement_met
    axis_b = reconcile_axis_b(
        axis_a, requirement_met, verdict.evidence_quote, library_entry, material_text
    )
    tag, approval_na = derive_intersection(axis_a, axis_b)

    evidence_valid = evidence_in_material(verdict.evidence_quote, material_text)
    if not evidence_valid:
        verdict_status = "needs_review"  # guardrail 4: invalid evidence degrades
    elif verdict.ambiguous:
        verdict_status = "needs_review"  # analyst judgment call (Aarvin ruling A)
    else:
        # a flag arises from EITHER axis: non-compliant (A) or drifted from
        # approval (B False) — drift is a finding type (04 §6e; GT-F03)
        verdict_status = "pass" if axis_a and axis_b is not False else "flag"

    return CheckOutcome(
        verdict_status=verdict_status,
        trigger_met=True,
        requirement_met=requirement_met,
        axis_a=axis_a,
        axis_b=axis_b,
        intersection_tag=tag,
        approval_na=approval_na,
        evidence_quote=verdict.evidence_quote,
        evidence_valid=evidence_valid,
        location=verdict.location,
        reason=verdict.reason,
        confidence=verdict.confidence,
    )


def production_invoke(model_string: str) -> Callable[[str], CheckerVerdict]:
    """Bind the checker schema to a chat model (init_chat_model string)."""
    from langchain.chat_models import init_chat_model

    # timeout is load-bearing: without it one dead connection hangs a whole
    # corpus run (E3 iter-2 postmortem, 2026-07-10)
    model = init_chat_model(
        model_string, temperature=0, timeout=90, max_retries=2
    ).with_structured_output(CheckerVerdict)

    def invoke(prompt: str) -> CheckerVerdict:
        return model.invoke(prompt)

    return invoke
