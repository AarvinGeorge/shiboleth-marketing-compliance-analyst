"""
meta:
  purpose: Pure per-flag trust signals. reliability_badge() maps structural
           checker signals (evidence validity, self-flagged ambiguity, needs
           review) to a qualitative strong/mixed/weak indicator. No I/O, no LLM.
           Advisory only: never affects a verdict, score, or state.
  contract: reliability_badge(evidence_valid, ambiguous, needs_review) -> str
            in {"strong","mixed","weak"}. None means "unknown" and is treated
            conservatively (never claims strong).
  deps: stdlib only.
"""

from __future__ import annotations


def reliability_badge(
    evidence_valid: bool | None,
    ambiguous: bool | None,
    needs_review: bool = False,
) -> str:
    """Qualitative trust for a single flag from structural signals.

    - Invalid evidence (the quoted text was not found in the material) is the
      hard failure and dominates -> "weak".
    - Any soft uncertainty (model self-flagged ambiguous, verdict needs review,
      or evidence validity is unknown) -> "mixed".
    - Valid evidence with no soft signal -> "strong".
    """
    if evidence_valid is False:
        return "weak"
    soft = (ambiguous is True) or bool(needs_review) or (evidence_valid is None)
    return "mixed" if soft else "strong"
