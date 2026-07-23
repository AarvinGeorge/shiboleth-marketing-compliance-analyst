"""
meta:
  purpose: Unit tests (first) for the KPI pure functions behind GET /metrics
           and the product metric row (01_spec §10). Math only, no DB: given
           already-fetched rows, assert the exact §10 definitions, adaptive
           time units, medians, and honest empty states.
  contract: every hero metric maps to its §10 definition; sublabels never
            assert units the data cannot substantiate; empty -> None value +
            honest note, never a placeholder number.
  deps: pytest.
"""

from datetime import UTC, datetime, timedelta

from adlign.services.scoring.kpis import (
    adaptive_duration,
    caught_metric,
    coverage_metric,
    median_duration,
    open_violations_metric,
    portfolio_score_metric,
    triage_metric,
)

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)


class TestAdaptiveDuration:
    def test_units_scale(self):
        assert adaptive_duration(timedelta(seconds=40)) == "40s"
        assert adaptive_duration(timedelta(minutes=5)) == "5m"
        assert adaptive_duration(timedelta(hours=14)) == "14h"
        assert adaptive_duration(timedelta(days=6)) == "6d"

    def test_days_take_precedence_over_hours(self):
        assert adaptive_duration(timedelta(days=2, hours=5)) == "2d"

    def test_none_for_empty(self):
        assert adaptive_duration(None) is None


class TestMedian:
    def test_odd(self):
        ds = [timedelta(hours=1), timedelta(hours=3), timedelta(hours=2)]
        assert median_duration(ds) == timedelta(hours=2)

    def test_even_averages_middle(self):
        ds = [timedelta(hours=2), timedelta(hours=4)]
        assert median_duration(ds) == timedelta(hours=3)

    def test_empty_is_none(self):
        assert median_duration([]) is None


class TestPortfolioScore:
    def test_severity_weighted_mean_over_products(self):
        # product A verified 80 (weight 3 materials), B verified 52 (weight 1)
        m = portfolio_score_metric([(80.0, 3), (52.0, 1)], trend=[70.0, 73.0])
        assert m["value"] == "73"  # (80*3 + 52*1)/4 = 73.0
        assert m["trend"] == [70.0, 73.0]  # REAL per-run series, verbatim

    def test_no_products_with_runs_is_empty(self):
        m = portfolio_score_metric([], trend=[])
        assert m["value"] is None
        assert "no" in m["sublabel"].lower()


class TestOpenViolations:
    def _flag(self, sev, opened_hours_ago, state="open"):
        return {"severity": sev, "opened_at": NOW - timedelta(hours=opened_hours_ago),
                "state": state}

    def test_counts_and_high_and_aging(self):
        flags = [self._flag("High", 14), self._flag("High", 3),
                 self._flag("Medium", 1), self._flag("Low", 30, state="dismissed")]
        m = open_violations_metric(flags, now=NOW)
        assert m["value"] == 3  # dismissed excluded
        assert "2 high" in m["sublabel"]
        assert "14h" in m["sublabel"]  # oldest open, adaptive unit

    def test_empty(self):
        m = open_violations_metric([], now=NOW)
        assert m["value"] == 0
        assert "high" not in m["sublabel"] or "0" in m["sublabel"]


class TestTriage:
    def test_count_and_median_ttd(self):
        undispositioned = 5
        ttds = [timedelta(hours=1), timedelta(hours=3)]
        m = triage_metric(undispositioned, ttds)
        assert m["value"] == 5
        assert "2h" in m["sublabel"]  # median

    def test_no_dispositions_is_honest(self):
        m = triage_metric(7, [])
        assert m["value"] == 7
        assert "no dispositions" in m["sublabel"].lower()


class TestCoverage:
    def test_pct_and_asset_count(self):
        m = coverage_metric(checked_recent=18, total_assets=20)
        assert m["value"] == "90%"
        assert "20" in m["sublabel"]

    def test_no_assets_empty(self):
        m = coverage_metric(checked_recent=0, total_assets=0)
        assert m["value"] is None


class TestCaught:
    def test_unapproved_and_drift(self):
        m = caught_metric(unapproved=3, drift=2)
        assert m["value"] == 5
        assert "3 unapproved" in m["sublabel"]
        assert "2 drift" in m["sublabel"]
        assert "this run" in m["sublabel"]  # honest window, not "this week"
