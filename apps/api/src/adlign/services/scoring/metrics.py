"""
meta:
  purpose: N7 scoring glue — aggregates checker outcomes into RunScores
           (draft, verified, per_property) via the pure formulas. Draft = all
           AI verdicts; verified = dismissed flags rescored as pass (FP).
  contract: outcomes_to_scores(outcomes, dismissed_ids) -> dict matching the
            RunScores schema + needs_review_count. Outcome dicts carry
            verdict_status, severity, property_id, optional flag_id.
  deps: adlign.services.scoring.formulas only.
"""

from __future__ import annotations

from collections import defaultdict

from adlign.services.scoring.formulas import product_score, property_score


def outcomes_to_scores(outcomes: list[dict], dismissed_ids: set[str]) -> dict:
    by_property: dict[str, list[dict]] = defaultdict(list)
    for o in outcomes:
        by_property[o.get("property_id", "unknown")].append(o)

    def scores(rescore_dismissed: bool) -> tuple[float | None, dict[str, float]]:
        per_property: dict[str, float] = {}
        weighted: list[tuple[float | None, int]] = []
        for prop, items in by_property.items():
            rows = []
            for o in items:
                status = o["verdict_status"]
                if (
                    rescore_dismissed
                    and status == "flag"
                    and o.get("flag_id") in dismissed_ids
                ):
                    status = "pass"
                rows.append({"verdict_status": status, "severity": o["severity"]})
            score = property_score(rows)
            scoreable = sum(1 for r in rows if r["verdict_status"] in ("pass", "flag"))
            if score is not None:
                per_property[prop] = round(score, 2)
            weighted.append((score, scoreable))
        product = product_score(weighted)
        return (round(product, 2) if product is not None else None), per_property

    draft, per_property = scores(rescore_dismissed=False)
    verified, _ = scores(rescore_dismissed=True)
    return {
        "draft": draft,
        "verified": verified,
        "per_property": per_property,
        "needs_review_count": sum(
            1 for o in outcomes if o["verdict_status"] == "needs_review"
        ),
    }
