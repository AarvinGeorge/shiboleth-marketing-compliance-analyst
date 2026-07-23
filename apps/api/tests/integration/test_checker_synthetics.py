"""
meta:
  purpose: THE M2 GATE (08 §4): the checker harness must correctly score ALL
           17 synthetic fixtures — including S17's exemption — before it ever
           sees a real page. Expectations come from the FROZEN ground truth
           (judgment_source=synthetic_author), never restated here.
  contract: per synthetic: verdict_status exact-match; axes + intersection tag
            match; evidence substring-valid on every flag. Runs from cassettes
            (replay) in CI; CASSETTE_MODE=record refreshes with live calls.
  deps: ground-truth/ (skipped if absent), cassettes fixture file; live
        recording additionally needs code/.env keys.
"""

import json
from pathlib import Path

import pytest

from adlign.config import REPO_ROOT, Settings
from adlign.db.seed import CHECKS
from adlign.db.seed_rules import D01_APPROVED_TEXT, RULES
from adlign.pipeline.nodes.check import run_check
from adlign.services.ingestion.corpus import load_corpus
from tests.support.cassette import cassette_invoke

GROUND_TRUTH = REPO_ROOT.parent / "ground-truth"
CASSETTE = Path(__file__).parent.parent / "fixtures" / "cassettes" / "checker_synthetics.json"

pytestmark = pytest.mark.skipif(
    not GROUND_TRUTH.exists(), reason="ground-truth/ not present"
)


def load_expectations() -> dict[str, dict]:
    data = json.loads((GROUND_TRUTH / "ground_truth.json").read_text(encoding="utf-8"))
    return {
        r["page_id"]: r
        for r in data["records"]
        if r["judgment_source"] == "synthetic_author"
    }


def rule_bundle(rule_id: str):
    rule_row = next(r for r in RULES if r[0] == rule_id)
    rule = {"id": rule_row[0], "verbatim_text": rule_row[1], "severity": rule_row[2]}
    checks = [c for c in CHECKS if c["rule_id"] == rule_id]
    library = (
        {"id": "D-01", "approved_text": D01_APPROVED_TEXT}
        if any(c["library_entry_id"] == "D-01" for c in checks)
        else None
    )
    return rule, checks, library


@pytest.fixture(scope="module")
def invoke():
    settings = Settings.from_env()
    model_string = settings.model_for("check")
    live = None
    import os

    if os.environ.get("CASSETTE_MODE") in ("record", "live"):
        from adlign.main import propagate_env
        from adlign.pipeline.nodes.check import production_invoke

        settings.verify()
        propagate_env(settings)
        live = production_invoke(model_string)
    return cassette_invoke(CASSETTE, model_string, live)


@pytest.fixture(scope="module")
def outcomes(invoke):
    docs = {d.page_id: d for d in load_corpus(GROUND_TRUTH / "snapshots-synthetic")}
    expectations = load_expectations()
    assert len(docs) == len(expectations) == 17
    results = {}
    for page_id, expected in sorted(expectations.items()):
        doc = docs[page_id]
        rule, checks, library = rule_bundle(expected["rule_id"])
        results[page_id] = (
            run_check(doc.body, rule, checks, library, invoke),
            expected,
            doc,
        )
    return results


def test_all_17_verdicts_match_ground_truth(outcomes):
    mismatches = [
        f"{pid}: got {out.verdict_status}, expected {exp['verdict_status']}"
        for pid, (out, exp, _d) in outcomes.items()
        if out.verdict_status != exp["verdict_status"]
    ]
    assert not mismatches, "M2 gate failed:\n" + "\n".join(mismatches)


def test_s17_exemption_is_not_applicable_never_pass(outcomes):
    out, exp, _doc = outcomes["S17"]
    assert exp["verdict_status"] == "not_applicable"  # frozen ground truth
    assert out.verdict_status == "not_applicable"
    assert out.trigger_met is False
    assert out.axis_a is None  # untriggered is N/A, NEVER pass (guardrail)


def test_axes_and_intersection_tags_match(outcomes):
    mismatches = []
    for pid, (out, exp, _d) in outcomes.items():
        if exp["verdict_status"] == "not_applicable":
            continue
        expected_b = exp["axis_b_matches_approval"]
        got_b = "na" if out.axis_b is None else out.axis_b
        if out.axis_a != exp["axis_a_compliant"] or got_b != expected_b:
            mismatches.append(f"{pid}: axes ({out.axis_a},{got_b}) "
                              f"vs ({exp['axis_a_compliant']},{expected_b})")
        elif out.intersection_tag != exp["intersection_tag"]:
            mismatches.append(f"{pid}: tag {out.intersection_tag} "
                              f"vs {exp['intersection_tag']}")
    assert not mismatches, "\n".join(mismatches)


def test_evidence_substring_valid_on_every_flag(outcomes):
    invalid = [
        pid
        for pid, (out, exp, doc) in outcomes.items()
        if out.verdict_status == "flag" and not out.evidence_valid
    ]
    assert not invalid, f"invalid evidence on: {invalid}"
