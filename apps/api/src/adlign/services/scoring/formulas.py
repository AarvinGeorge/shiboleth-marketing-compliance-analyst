"""
meta:
  purpose: Pure scoring + verdict math. THE single source (07 §6) for the
           intersection-tag derivation, lifecycle transition rules, severity
           weights, property/product scores, the content-hash convention, and
           the freshness policy. No LLM, no DB, no I/O — ever.
  contract: property_score: 100×weighted(pass)/weighted(pass+fail), N/A and
            needs_review excluded, None when nothing scoreable. product_score:
            material-count-weighted mean, unscored properties skipped.
            derive_intersection(axis_a, axis_b|None) -> (tag, approval_na).
            validate_transition raises InvalidTransition (04 §6e lifecycle;
            dismissed terminal from open only). content_hash = sha256 of
            .strip()ed text (ground-truth README convention).
  deps: stdlib only. Changes here are contract changes: surface to Aarvin.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

SEVERITY_WEIGHTS: dict[str, int] = {"High": 3, "Medium": 2, "Low": 1}

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"confirmed", "dismissed"}),
    "confirmed": frozenset({"assigned"}),
    "assigned": frozenset({"fix_pending_verification"}),
    "fix_pending_verification": frozenset({"closed"}),
    "closed": frozenset(),
    "dismissed": frozenset(),
}


class InvalidTransition(ValueError):
    """Raised for lifecycle moves outside ALLOWED_TRANSITIONS."""


def severity_weight(severity: str) -> int:
    return SEVERITY_WEIGHTS[severity]  # KeyError on unknown: intended


def property_score(results: list[dict]) -> float | None:
    """01_spec §5: N/A and needs_review are excluded from the denominator;
    untriggered is N/A, never pass (guardrail). None when nothing scoreable."""
    passed = sum(
        severity_weight(r["severity"]) for r in results if r["verdict_status"] == "pass"
    )
    failed = sum(
        severity_weight(r["severity"]) for r in results if r["verdict_status"] == "flag"
    )
    denominator = passed + failed
    if denominator == 0:
        return None
    return 100.0 * passed / denominator


def product_score(per_property: list[tuple[float | None, int]]) -> float | None:
    """Weighted mean over properties by material count; unscored skipped."""
    scored = [(score, count) for score, count in per_property if score is not None]
    total = sum(count for _, count in scored)
    if total == 0:
        return None
    return sum(score * count for score, count in scored) / total


def derive_intersection(axis_a: bool, axis_b: bool | None) -> tuple[str, bool]:
    """07 §6: B=None (na) derives from A alone with the approval_na marker."""
    if axis_b is None:
        return ("all_good" if axis_a else "unapproved_violation", True)
    match (axis_a, axis_b):
        case (True, True):
            return ("all_good", False)
        case (True, False):
            return ("drifted_but_compliant", False)
        case (False, True):
            return ("approved_but_non_compliant", False)
        case _:
            return ("unapproved_violation", False)


def recommended_severity(rule_severity: str, intersection_tag: str | None) -> str:
    """Matrix-aware severity recommendation (2026-07-14, Aarvin-approved).
    The rule's scorecard severity is the CEILING (how bad a violation of
    this rule is); the compliance-vs-approval matrix says what actually
    happened. drifted_but_compliant = compliant content whose wording left
    the approved library — governance risk, not regulatory risk — so it
    recommends Low regardless of the rule. Violations (either axis failing
    compliance) keep the rule severity; unresolved tags (needs-review
    all_good / na) keep the rule severity as the unresolved worst case.
    Human override still wins everywhere: effective = override ?? this."""
    if intersection_tag == "drifted_but_compliant":
        return "Low"
    return rule_severity


def validate_transition(current: str, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None or target not in ALLOWED_TRANSITIONS:
        raise InvalidTransition(f"unknown lifecycle state: {current!r} -> {target!r}")
    if target not in allowed:
        raise InvalidTransition(f"illegal transition {current!r} -> {target!r}")


def content_hash(text: str) -> str:
    """Ground-truth README convention: sha256 of the whitespace-stripped body."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def is_fresh(fetched_at: datetime, ttl_hours: float = 24.0) -> bool:
    """Cache/dedup refinement (04 §6g): fetch only missing or stale."""
    age = datetime.now(UTC) - fetched_at
    return age.total_seconds() < ttl_hours * 3600
