"""
meta:
  purpose: Pure KPI functions behind GET /metrics and the U6 product metric
           row (01_spec §10, the research-backed analyst KPIs — names and
           definitions are canonical, do not invent alternatives). Each takes
           already-fetched rows and returns {value, sublabel, intent?, trend?}.
           value=None + honest sublabel when the DB cannot substantiate it
           (never a placeholder number). Adaptive time units until real days
           exist. No DB, no I/O — the route does the SQL and calls these.
  contract: portfolio_score_metric, open_violations_metric, triage_metric,
            coverage_metric, caught_metric + adaptive_duration/median_duration.
  deps: stdlib only.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# The §10 intent line per metric: the analyst question it answers.
INTENT = {
    "portfolio_score": "Are we getting safer or riskier? The bank-partner number.",
    "open_violations": "What is exposed, and how long has it festered?",
    "triage": "Is the review queue under control?",
    "coverage": "Can I attest to what is live? The exam-readiness answer.",
    "caught": "Is anything shipping around the approval process?",
}


def adaptive_duration(delta: timedelta | None) -> str | None:
    """Coarsest honest unit: days > hours > minutes > seconds. No fabricated
    '7-day' framing until real days of history exist."""
    if delta is None:
        return None
    secs = int(delta.total_seconds())
    if secs >= 86_400:
        return f"{secs // 86_400}d"
    if secs >= 3_600:
        return f"{secs // 3_600}h"
    if secs >= 60:
        return f"{secs // 60}m"
    return f"{secs}s"


def median_duration(deltas: list[timedelta]) -> timedelta | None:
    if not deltas:
        return None
    s = sorted(deltas)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def portfolio_score_metric(
    per_product: list[tuple[float | None, int]], trend: list[float]
) -> dict:
    """Severity-weighted verified mean over products with runs (§10.1). Trend
    is the REAL per-run verified series only — no fabricated 7-day history."""
    scored = [(v, w) for v, w in per_product if v is not None]
    total = sum(w for _v, w in scored)
    if total == 0:
        return {"value": None, "sublabel": "no scored runs yet",
                "trend": [], "intent": INTENT["portfolio_score"]}
    mean = sum(v * w for v, w in scored) / total
    return {"value": str(round(mean)), "sublabel": "verified, per-run trend",
            "trend": trend, "intent": INTENT["portfolio_score"]}


def open_violations_metric(flags: list[dict], now: datetime) -> dict:
    """Open/confirmed flags by severity + real aging (§10.2). A flag row:
    {severity, opened_at, state}. Aging reference = the flag's run.started_at
    (flags open when their run creates them)."""
    open_flags = [f for f in flags if f["state"] not in ("dismissed", "closed")]
    high = sum(1 for f in open_flags if f["severity"] == "High")
    oldest = adaptive_duration(
        max((now - f["opened_at"] for f in open_flags), default=None)
    )
    if not open_flags:
        return {"value": 0, "sublabel": "none open",
                "intent": INTENT["open_violations"]}
    parts = [f"{high} high"] if high else []
    if oldest:
        parts.append(f"oldest open {oldest}")
    return {"value": len(open_flags), "sublabel": " · ".join(parts) or "open",
            "intent": INTENT["open_violations"]}


def triage_metric(undispositioned: int, ttds: list[timedelta]) -> dict:
    """Awaiting-triage count + median time to disposition (§10.3)."""
    med = median_duration(ttds)
    sub = (f"median disposition {adaptive_duration(med)}" if med
           else "no dispositions yet")
    return {"value": undispositioned, "sublabel": sub, "intent": INTENT["triage"]}


def coverage_metric(checked_recent: int, total_assets: int) -> dict:
    """% of tracked assets checked <=24h + true asset count (§10.4)."""
    if total_assets == 0:
        return {"value": None, "sublabel": "no assets tracked yet",
                "intent": INTENT["coverage"]}
    pct = round(100 * checked_recent / total_assets)
    return {"value": f"{pct}%", "sublabel": f"{total_assets} assets tracked",
            "intent": INTENT["coverage"]}


def caught_metric(unapproved: int, drift: int) -> dict:
    """Reconciliation finds: unapproved + drift (§10.5). Honest window label
    ('this run') until a week of history exists."""
    return {"value": unapproved + drift,
            "sublabel": f"{unapproved} unapproved · {drift} drift, this run",
            "intent": INTENT["caught"]}
