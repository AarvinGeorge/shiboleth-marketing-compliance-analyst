"""
meta:
  purpose: Measured checker accuracy per rule — the honest number shown to
           analysts in place of the LLM's self-reported confidence, which
           trace analysis (2026-07-14, 1,552 verdicts) proved uncalibrated:
           flag verdicts cluster at 0.95 as a stereotyped house number and
           the worst-measured rule (R-03, 65%) self-reports the HIGHEST
           confidence. Values here come from the FROZEN ground-truth v2
           certification (../../ground-truth-v2/results/e5v2-final.json,
           strict per-rule accuracy, locked 2026-07-13).
  contract: measured_accuracy(check_or_rule_id) -> {"accuracy": float,
            "source": str} | None. None = the rule has never been certified
            (e.g. Customize-layer custom rules): callers MUST surface that
            as "not yet measured", never borrow another rule's number.
            Re-certification updates MEASURED_ACCURACY + SOURCE here, in
            one place; every payload follows.
  deps: stdlib only.
"""

from __future__ import annotations

SOURCE = "ground truth v2 certification, 2026-07-13 (e5v2-final, strict)"

# per-rule strict accuracy from the locked GT v2 run; overall 78.8%
# (train 80.6 / held-out test 74.1)
MEASURED_ACCURACY: dict[str, float] = {
    "R-01": 0.809,
    "R-02": 0.737,
    "R-03": 0.650,
    "R-04": 1.0,
}


def rule_id_of(check_or_rule_id: str) -> str:
    """R-01-REQ / R-01-TRIG -> R-01; bare rule ids pass through."""
    head, sep, tail = check_or_rule_id.rpartition("-")
    if tail in ("REQ", "TRIG") and head:
        return head
    return check_or_rule_id


def measured_accuracy(check_or_rule_id: str) -> dict | None:
    accuracy = MEASURED_ACCURACY.get(rule_id_of(check_or_rule_id))
    if accuracy is None:
        return None
    return {"accuracy": accuracy, "source": SOURCE}
