"""
meta:
  purpose: Unit tests (first) for the public-demo hardening layer: env-driven
           Settings accessors (PAGE_CAP_MAX, CHECKS_RATE_LIMIT_PER_HOUR,
           PROTECTED_RUN_IDS, CORS_ALLOW_ORIGINS), the sliding-window
           RateLimiter, and the effective_page_cap clamp. Defaults must keep
           dev behavior unchanged (no cap change, limiter off, nothing
           protected, CORS = local web app only).
  contract: Settings.page_cap_max default 20; checks_rate_limit_per_hour
            default 0 (disabled); protected_run_ids default empty frozenset,
            parsed from a comma list with whitespace tolerance;
            cors_allow_origins default ("http://localhost:3000",), parsed
            from a comma list preserving order. RateLimiter
            allows N hits per window per key, expires old hits, and is a
            no-op at limit 0. effective_page_cap = min(requested, max).
  deps: pytest; adlign.config, adlign.api.hardening.
"""

from adlign.api.hardening import RateLimiter, effective_page_cap
from tests.unit.test_config import make_settings


class TestSettingsAccessors:
    def test_page_cap_max_defaults_to_20(self):
        assert make_settings().page_cap_max == 20

    def test_page_cap_max_reads_env(self):
        assert make_settings(PAGE_CAP_MAX="8").page_cap_max == 8

    def test_rate_limit_defaults_to_disabled(self):
        assert make_settings().checks_rate_limit_per_hour == 0

    def test_rate_limit_reads_env(self):
        assert make_settings(CHECKS_RATE_LIMIT_PER_HOUR="3").checks_rate_limit_per_hour == 3

    def test_protected_run_ids_default_empty(self):
        assert make_settings().protected_run_ids == frozenset()

    def test_protected_run_ids_parses_comma_list_with_whitespace(self):
        settings = make_settings(PROTECTED_RUN_IDS=" abc123 , def456,, ")
        assert settings.protected_run_ids == frozenset({"abc123", "def456"})

    def test_cors_origins_default_is_dev_web_app(self):
        assert make_settings().cors_allow_origins == ("http://localhost:3000",)

    def test_cors_origins_blank_falls_back_to_default(self):
        settings = make_settings(CORS_ALLOW_ORIGINS="  ")
        assert settings.cors_allow_origins == ("http://localhost:3000",)

    def test_cors_origins_parses_comma_list_with_whitespace(self):
        settings = make_settings(
            CORS_ALLOW_ORIGINS=" https://marketing-compliance-analysis-tool.vercel.app , http://localhost:3000,, "
        )
        assert settings.cors_allow_origins == (
            "https://marketing-compliance-analysis-tool.vercel.app",
            "http://localhost:3000",
        )


class TestEffectivePageCap:
    def test_requested_above_max_is_clamped(self):
        assert effective_page_cap(20, make_settings(PAGE_CAP_MAX="8")) == 8

    def test_requested_below_max_is_kept(self):
        assert effective_page_cap(3, make_settings(PAGE_CAP_MAX="8")) == 3

    def test_default_max_keeps_dev_default_request(self):
        assert effective_page_cap(20, make_settings()) == 20


class TestRateLimiter:
    def test_allows_up_to_limit_then_blocks(self):
        now = [1000.0]
        limiter = RateLimiter(limit=2, window_seconds=3600, clock=lambda: now[0])
        assert limiter.allow("ip-1") is True
        assert limiter.allow("ip-1") is True
        assert limiter.allow("ip-1") is False

    def test_keys_are_independent(self):
        now = [1000.0]
        limiter = RateLimiter(limit=1, window_seconds=3600, clock=lambda: now[0])
        assert limiter.allow("ip-1") is True
        assert limiter.allow("ip-2") is True
        assert limiter.allow("ip-1") is False

    def test_hits_expire_after_the_window(self):
        now = [1000.0]
        limiter = RateLimiter(limit=1, window_seconds=3600, clock=lambda: now[0])
        assert limiter.allow("ip-1") is True
        assert limiter.allow("ip-1") is False
        now[0] += 3601
        assert limiter.allow("ip-1") is True

    def test_limit_zero_never_blocks(self):
        limiter = RateLimiter(limit=0, window_seconds=3600, clock=lambda: 0.0)
        for _ in range(50):
            assert limiter.allow("ip-1") is True
