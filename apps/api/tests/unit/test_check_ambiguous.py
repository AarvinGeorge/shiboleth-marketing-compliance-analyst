"""
meta:
  purpose: Stage 1 trust: the checker's self-flagged `ambiguous` must survive
           into the CheckOutcome so it can be persisted on the flag. No LLM
           (stub invoke). Advisory only: does not change the verdict logic.
  deps: pytest; adlign.pipeline.nodes.check.
"""

from adlign.pipeline.nodes.check import CheckerVerdict, run_check

RULE = {"verbatim_text": "rule text"}
CHECKS = [
    {"kind": "trigger", "text": "t", "evidence_criteria": "tc"},
    {"kind": "requirement", "text": "r", "evidence_criteria": "rc"},
]
MATERIAL = "we advertise free filing for everyone."


def _invoke(ambiguous: bool):
    def invoke(_prompt: str) -> CheckerVerdict:
        return CheckerVerdict(
            trigger_met=True,
            requirement_met=False,
            evidence_quote="free filing",
            location="body",
            reason="stub",
            confidence=0.9,
            ambiguous=ambiguous,
        )

    return invoke


def test_outcome_carries_ambiguous_true():
    outcome = run_check(MATERIAL, RULE, CHECKS, None, _invoke(ambiguous=True))
    assert outcome.ambiguous is True


def test_outcome_carries_ambiguous_false():
    outcome = run_check(MATERIAL, RULE, CHECKS, None, _invoke(ambiguous=False))
    assert outcome.ambiguous is False
