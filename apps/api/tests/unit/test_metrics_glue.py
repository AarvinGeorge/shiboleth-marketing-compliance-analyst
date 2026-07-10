"""
meta:
  purpose: Unit tests (first) for N7 scoring glue: CheckOutcome lists ->
           per-property scores -> RunScores. Pure aggregation over
           formulas.py; no LLM, no DB.
  contract: outcomes_to_scores maps verdict_status+severity through
            property_score/product_score; needs_review counted separately;
            draft vs verified derived from flag states.
  deps: pytest.
"""

from shiboleth.services.scoring.metrics import outcomes_to_scores


def outcome(status: str, severity: str = "High", property_id: str = "tt-website"):
    return {"verdict_status": status, "severity": severity, "property_id": property_id}


def test_draft_scores_per_property_and_product():
    outcomes = [
        outcome("pass"), outcome("flag"),               # website: 50.0 (High/High)
        outcome("pass", "Low", "tt-instagram"),          # instagram: 100.0
        outcome("not_applicable", "High", "tt-instagram"),
    ]
    scores = outcomes_to_scores(outcomes, dismissed_ids=set())
    assert scores["per_property"]["tt-website"] == 50.0
    assert scores["per_property"]["tt-instagram"] == 100.0
    # product: weighted by scoreable material count (2 website, 1 instagram)
    assert scores["draft"] == round((50.0 * 2 + 100.0 * 1) / 3, 2)


def test_verified_rescores_dismissed_flags_as_pass():
    outcomes = [
        {**outcome("flag"), "flag_id": "f1"},
        {**outcome("pass"), "flag_id": None},
    ]
    scores = outcomes_to_scores(outcomes, dismissed_ids={"f1"})
    assert scores["draft"] == 50.0
    assert scores["verified"] == 100.0


def test_needs_review_excluded_but_counted():
    outcomes = [outcome("pass"), outcome("needs_review")]
    scores = outcomes_to_scores(outcomes, dismissed_ids=set())
    assert scores["draft"] == 100.0
    assert scores["needs_review_count"] == 1


def test_empty_outcomes():
    scores = outcomes_to_scores([], dismissed_ids=set())
    assert scores["draft"] is None and scores["verified"] is None
