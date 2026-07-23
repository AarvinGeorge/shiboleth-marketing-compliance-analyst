"""
meta:
  purpose: Unit tests for scoring/formulas.py — written BEFORE implementation
           (TDD). Covers 01_spec §5 scoring math, 07 §6 intersection-tag
           derivation (single source), 04 §6e lifecycle transitions, the
           content-hash convention, and the freshness policy.
  contract: pure functions only; no DB, no LLM, no I/O.
  deps: pytest.
"""

from datetime import UTC, datetime, timedelta

import pytest

from adlign.services.scoring.formulas import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    content_hash,
    derive_intersection,
    is_fresh,
    product_score,
    property_score,
    severity_weight,
    validate_transition,
)


# --- severity weights (High 3 / Medium 2 / Low 1) ---------------------------

def test_severity_weights():
    assert severity_weight("High") == 3
    assert severity_weight("Medium") == 2
    assert severity_weight("Low") == 1


def test_unknown_severity_raises():
    with pytest.raises(KeyError):
        severity_weight("Critical")


# --- property score ----------------------------------------------------------
# score = 100 × weighted(pass) / weighted(pass+fail); N/A and needs_review
# excluded from the denominator (untriggered is N/A, never pass — guardrail).

def v(status: str, severity: str = "High") -> dict:
    return {"verdict_status": status, "severity": severity}


def test_all_pass_is_100():
    assert property_score([v("pass"), v("pass", "Low")]) == 100.0


def test_all_fail_is_0():
    assert property_score([v("flag"), v("flag", "Medium")]) == 0.0


def test_na_and_needs_review_excluded_from_denominator():
    results = [v("pass"), v("not_applicable"), v("needs_review")]
    assert property_score(results) == 100.0


def test_severity_weighting():
    # High pass (3) + Low fail (1) -> 100 * 3/4 = 75
    assert property_score([v("pass", "High"), v("flag", "Low")]) == 75.0


def test_no_scoreable_checks_returns_none():
    assert property_score([v("not_applicable"), v("needs_review")]) is None
    assert property_score([]) is None


def test_dismissed_flag_counts_as_pass_in_verified_score():
    # Verified score: a dismissed flag (false positive) rescores as pass.
    draft = [v("flag"), v("pass")]
    assert property_score(draft) == 50.0
    verified = [v("pass"), v("pass")]  # after dismissal recompute
    assert property_score(verified) == 100.0


# --- product score (weighted mean over properties by material count) ---------

def test_product_score_weighted_by_material_count():
    # prop A: score 100, 3 materials; prop B: score 50, 1 material -> 87.5
    assert product_score([(100.0, 3), (50.0, 1)]) == 87.5


def test_product_score_skips_unscored_properties():
    assert product_score([(100.0, 2), (None, 5)]) == 100.0


def test_product_score_all_unscored_is_none():
    assert product_score([(None, 2), (None, 1)]) is None


# --- intersection tag derivation (07 §6, single source) ----------------------

@pytest.mark.parametrize(
    "axis_a,axis_b,tag,approval_na",
    [
        (True, True, "all_good", False),
        (True, False, "drifted_but_compliant", False),
        (False, True, "approved_but_non_compliant", False),
        (False, False, "unapproved_violation", False),
        (True, None, "all_good", True),
        (False, None, "unapproved_violation", True),
    ],
)
def test_derive_intersection(axis_a, axis_b, tag, approval_na):
    assert derive_intersection(axis_a, axis_b) == (tag, approval_na)


# --- lifecycle (04 §6e: open → confirmed → assigned → fix_pending_verification
#     → closed; dismissed terminal from open) ---------------------------------

def test_happy_path_transitions_allowed():
    chain = ["open", "confirmed", "assigned", "fix_pending_verification", "closed"]
    for frm, to in zip(chain, chain[1:]):
        validate_transition(frm, to)  # must not raise


def test_dismiss_only_from_open():
    validate_transition("open", "dismissed")
    for frm in ("confirmed", "assigned", "fix_pending_verification", "closed"):
        with pytest.raises(InvalidTransition):
            validate_transition(frm, "dismissed")


def test_terminal_states_have_no_exits():
    assert ALLOWED_TRANSITIONS["closed"] == frozenset()
    assert ALLOWED_TRANSITIONS["dismissed"] == frozenset()


def test_no_skipping_states():
    with pytest.raises(InvalidTransition):
        validate_transition("open", "assigned")
    with pytest.raises(InvalidTransition):
        validate_transition("confirmed", "closed")


def test_unknown_state_raises():
    with pytest.raises(InvalidTransition):
        validate_transition("open", "archived")


# --- content hash (ground-truth convention: sha256 of stripped text) ---------

def test_content_hash_strips_whitespace():
    assert content_hash("  hello \n") == content_hash("hello")


def test_content_hash_known_value():
    import hashlib
    assert content_hash("hello") == hashlib.sha256(b"hello").hexdigest()


# --- freshness policy (TTL default 24h) --------------------------------------

def test_fresh_within_ttl():
    fetched = datetime.now(UTC) - timedelta(hours=1)
    assert is_fresh(fetched, ttl_hours=24) is True


def test_stale_beyond_ttl():
    fetched = datetime.now(UTC) - timedelta(hours=25)
    assert is_fresh(fetched, ttl_hours=24) is False


# --- matrix-aware recommended severity (2026-07-14: risk follows the
#     compliance-vs-approval matrix, not the rule alone; Aarvin-approved) -----

def test_drift_recommends_low_regardless_of_rule_severity():
    from adlign.services.scoring.formulas import recommended_severity

    assert recommended_severity("High", "drifted_but_compliant") == "Low"
    assert recommended_severity("Medium", "drifted_but_compliant") == "Low"
    assert recommended_severity("Low", "drifted_but_compliant") == "Low"


def test_violations_keep_rule_severity():
    from adlign.services.scoring.formulas import recommended_severity

    for tag in ("unapproved_violation", "approved_but_non_compliant"):
        assert recommended_severity("High", tag) == "High"
        assert recommended_severity("Medium", tag) == "Medium"


def test_unresolved_tags_keep_rule_severity_worst_case():
    # needs-review flags can carry all_good or an unknown/na tag; the
    # unresolved worst case is the rule severity, never an upgrade
    from adlign.services.scoring.formulas import recommended_severity

    assert recommended_severity("High", "all_good") == "High"
    assert recommended_severity("Medium", "na") == "Medium"


# --- measured-accuracy calibration (GT v2 certification, e5v2-final) ---------

def test_measured_accuracy_known_rules():
    from adlign.services.scoring.calibration import measured_accuracy

    a1 = measured_accuracy("R-01-REQ")
    a3 = measured_accuracy("R-03-REQ")
    assert a1 is not None and a3 is not None
    assert 0.0 < a3["accuracy"] < a1["accuracy"] <= 1.0
    assert a1["source"]  # provenance string is part of the disclosure


def test_measured_accuracy_unknown_rule_is_honest_none():
    # custom rules added via the Customize layer have no certification yet:
    # the API must say "not measured", never borrow another rule's number
    from adlign.services.scoring.calibration import measured_accuracy

    assert measured_accuracy("CUSTOM-ab12-REQ") is None
