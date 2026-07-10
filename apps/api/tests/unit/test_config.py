"""
meta:
  purpose: Unit tests for shiboleth.config — env verification, key masking,
           per-stage model registry. Written BEFORE config.py (TDD).
  contract: Settings.from_env(mapping) never reads the real environment when a
            mapping is given; verify() raises EnvError listing every missing
            required key; mask() never reveals a full secret.
  deps: pytest
"""

import pytest

from shiboleth.config import EnvError, Settings, mask

REQUIRED = {
    "DATABASE_URL": "postgresql+asyncpg://shiboleth:shiboleth@localhost:5432/shiboleth",
    "LANGSMITH_API_KEY": "lsv2_pt_abcdef1234567890",
    "GOOGLE_API_KEY": "AIzaSyFAKEFAKEFAKEFAKE",
    "GROQ_API_KEY": "gsk_fakefakefakefake",
}


def make_settings(**overrides) -> Settings:
    env = {**REQUIRED, **overrides}
    return Settings.from_env(env)


class TestVerify:
    def test_all_required_present_passes(self):
        settings = make_settings()
        settings.verify()  # must not raise

    def test_missing_one_required_key_raises_and_names_it(self):
        env = {k: v for k, v in REQUIRED.items() if k != "GROQ_API_KEY"}
        settings = Settings.from_env(env)
        with pytest.raises(EnvError, match="GROQ_API_KEY"):
            settings.verify()

    def test_missing_several_keys_all_named(self):
        settings = Settings.from_env({"DATABASE_URL": REQUIRED["DATABASE_URL"]})
        with pytest.raises(EnvError) as exc:
            settings.verify()
        for key in ("LANGSMITH_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
            assert key in str(exc.value)

    def test_blank_value_counts_as_missing(self):
        settings = make_settings(GOOGLE_API_KEY="   ")
        with pytest.raises(EnvError, match="GOOGLE_API_KEY"):
            settings.verify()

    def test_optional_keys_do_not_block(self):
        settings = make_settings()  # no OPENAI_API_KEY / ANTHROPIC_API_KEY
        settings.verify()
        assert settings.openai_api_key is None
        assert settings.anthropic_api_key is None


class TestMask:
    def test_mask_hides_middle(self):
        secret = "lsv2_pt_abcdef1234567890"
        masked = mask(secret)
        assert secret not in masked
        assert masked.startswith("lsv2")
        assert masked.endswith("90")

    def test_mask_short_values_fully_hidden(self):
        assert mask("abc") == "****"
        assert mask("") == "****"

    def test_masked_echo_contains_no_secret(self):
        settings = make_settings()
        echo = settings.masked_echo()
        for value in REQUIRED.values():
            assert value not in echo
        assert "LANGSMITH_API_KEY" in echo


class TestModelRegistry:
    def test_defaults_per_stage(self):
        # check = Anthropic Haiku (Aarvin 2026-07-10, paid approved: Groq's
        # 100k TPD cap cannot carry corpus-scale E3); cheap stages stay Groq.
        settings = make_settings()
        assert settings.model_for("check") == "anthropic:claude-haiku-4-5"
        for stage in ("extract", "cluster_label", "report"):
            assert settings.model_for(stage) == "groq:llama-3.3-70b-versatile"

    def test_env_override_wins(self):
        settings = make_settings(DEFAULT_MODEL_CHECK="anthropic:claude-sonnet-5")
        assert settings.model_for("check") == "anthropic:claude-sonnet-5"

    def test_unknown_stage_raises(self):
        settings = make_settings()
        with pytest.raises(KeyError):
            settings.model_for("nonexistent_stage")


class TestLangSmith:
    def test_project_default(self):
        settings = make_settings()
        assert settings.langsmith_project == "shiboleth-marketing-compliance-analyst-project"
        assert settings.langsmith_tracing is True

    def test_tracing_false_when_env_says_so(self):
        settings = make_settings(LANGSMITH_TRACING="false")
        assert settings.langsmith_tracing is False
