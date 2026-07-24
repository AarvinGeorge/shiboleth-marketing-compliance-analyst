"""
meta:
  purpose: Unit tests for the pure reliability_badge trust function. No I/O.
  deps: pytest; adlign.services.scoring.trust.
"""

from adlign.services.scoring.trust import reliability_badge


def test_strong_when_valid_and_unambiguous():
    assert reliability_badge(evidence_valid=True, ambiguous=False, needs_review=False) == "strong"


def test_strong_when_ambiguous_is_unknown():
    assert reliability_badge(evidence_valid=True, ambiguous=None, needs_review=False) == "strong"


def test_mixed_when_ambiguous():
    assert reliability_badge(evidence_valid=True, ambiguous=True, needs_review=False) == "mixed"


def test_mixed_when_needs_review():
    assert reliability_badge(evidence_valid=True, ambiguous=False, needs_review=True) == "mixed"


def test_weak_when_evidence_invalid():
    assert reliability_badge(evidence_valid=False, ambiguous=False, needs_review=False) == "weak"


def test_weak_evidence_invalid_dominates():
    assert reliability_badge(evidence_valid=False, ambiguous=True, needs_review=True) == "weak"


def test_none_evidence_valid_is_not_strong():
    assert reliability_badge(evidence_valid=None, ambiguous=None, needs_review=False) == "mixed"


def test_needs_review_defaults_false():
    assert reliability_badge(evidence_valid=True, ambiguous=False) == "strong"
