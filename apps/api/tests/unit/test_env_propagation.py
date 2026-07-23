"""
meta:
  purpose: Unit tests for propagate_env — LangChain integrations read secrets
           from process env, so Settings must export provider keys + LangSmith
           config to os.environ. Written before the fix (TDD; caught live at
           the M0 gate: Gemini call failed with key present in .env only).
  contract: propagate_env exports GOOGLE_API_KEY, GROQ_API_KEY, LangSmith
            vars; optional keys only when set; never writes blank values.
  deps: pytest (monkeypatch isolates os.environ).
"""

import os

from adlign.config import Settings
from adlign.main import propagate_env

BASE = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
    "LANGSMITH_API_KEY": "lsv2_pt_test1234567890",
    "GOOGLE_API_KEY": "AQ.testgooglekey123",
    "GROQ_API_KEY": "gsk_testgroqkey123",
}

VARS = (
    "GOOGLE_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "LANGSMITH_API_KEY", "LANGSMITH_TRACING", "LANGSMITH_PROJECT",
)


def clean_env(monkeypatch):
    for var in VARS:
        monkeypatch.delenv(var, raising=False)


def test_provider_keys_exported(monkeypatch):
    clean_env(monkeypatch)
    propagate_env(Settings.from_env(BASE))
    assert os.environ["GOOGLE_API_KEY"] == BASE["GOOGLE_API_KEY"]
    assert os.environ["GROQ_API_KEY"] == BASE["GROQ_API_KEY"]
    assert os.environ["LANGSMITH_API_KEY"] == BASE["LANGSMITH_API_KEY"]
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "adlign-production"


def test_optional_keys_absent_stay_absent(monkeypatch):
    clean_env(monkeypatch)
    propagate_env(Settings.from_env(BASE))
    assert "OPENAI_API_KEY" not in os.environ
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_optional_keys_present_are_exported(monkeypatch):
    clean_env(monkeypatch)
    propagate_env(Settings.from_env({**BASE, "ANTHROPIC_API_KEY": "sk-ant-test"}))
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"
