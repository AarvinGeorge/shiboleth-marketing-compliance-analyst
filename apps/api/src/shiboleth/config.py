"""
meta:
  purpose: Single source of env config for the Shiboleth API. Loads code/.env
           (python-dotenv), verifies required keys at startup with a masked
           echo (02_handoff §2), and owns the per-stage model registry
           (init_chat_model provider strings, 01_spec §4 model policy).
  contract: Settings.from_env(mapping|None) — mapping injection for tests,
            None reads code/.env + os.environ. verify() raises EnvError naming
            every missing required key. model_for(stage) -> provider string;
            stages: extract | check | cluster_label | report.
  deps: python-dotenv. Secrets are read HERE and nowhere else (guardrail).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

# code/apps/api/src/shiboleth/config.py -> parents[4] == code/
REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = REPO_ROOT / ".env"

REQUIRED_KEYS = ("DATABASE_URL", "LANGSMITH_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY")

# Stage -> (env override var, default init_chat_model string).
# check = anthropic:claude-haiku-4-5 (Aarvin, 2026-07-10, PAID approved):
# Groq's hidden 100k tokens-per-DAY cap (visible only in 429 bodies, not
# headers) cannot carry corpus-scale E3 runs — ~$1/full run on Haiku vs a
# hard daily wall. Cheap stages stay Groq ($0; small payloads fit TPD).
# Pinned ids, never "-latest": the E3 loop and base condition need stable
# model identities.
MODEL_STAGES: dict[str, tuple[str, str]] = {
    "extract": ("DEFAULT_MODEL_EXTRACT", "groq:llama-3.3-70b-versatile"),
    "check": ("DEFAULT_MODEL_CHECK", "anthropic:claude-haiku-4-5"),
    "cluster_label": ("DEFAULT_MODEL_CLUSTER_LABEL", "groq:llama-3.3-70b-versatile"),
    "report": ("DEFAULT_MODEL_REPORT", "groq:llama-3.3-70b-versatile"),
    # issue layer (clustering C1): signer + adjudicator; Anthropic per
    # Aarvin 2026-07-13, cheap tier — two short calls per wording cluster
    "issue": ("DEFAULT_MODEL_ISSUE", "anthropic:claude-haiku-4-5"),
    # customize layer: rule -> binary decomposition + retrieval keywords
    "decompose": ("DEFAULT_MODEL_DECOMPOSE", "anthropic:claude-haiku-4-5"),
    # semantic page discovery: URL relevance ranking vs the live scorecard
    "discover": ("DEFAULT_MODEL_DISCOVER", "anthropic:claude-haiku-4-5"),
}

LANGSMITH_PROJECT_DEFAULT = "shiboleth-marketing-compliance-analyst-project"


class EnvError(RuntimeError):
    """Raised at startup when required env keys are missing or blank."""


def mask(value: str) -> str:
    """Mask a secret for log echo: first 4 + last 2 chars, never the middle."""
    if len(value) < 8:
        return "****"
    return f"{value[:4]}…{value[-2:]}"


def redact_db_url(url: str) -> str:
    """Redact the password segment of a database URL for log echo."""
    return re.sub(r"(://[^:/@]+):[^@]+@", r"\1:****@", url)


@dataclass(frozen=True)
class Settings:
    env: Mapping[str, str] = field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        if environ is not None:
            return cls(env=dict(environ))
        merged: dict[str, str] = {
            k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None
        }
        merged.update(os.environ)
        return cls(env=merged)

    def _get(self, key: str) -> str | None:
        value = self.env.get(key)
        if value is None or not value.strip():
            return None
        return value.strip()

    def verify(self) -> None:
        missing = [k for k in REQUIRED_KEYS if self._get(k) is None]
        if missing:
            raise EnvError(
                "Missing required env keys (set them in code/.env): "
                + ", ".join(missing)
            )

    def masked_echo(self) -> str:
        lines = []
        for key in REQUIRED_KEYS + ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            value = self._get(key)
            if key == "DATABASE_URL":
                shown = redact_db_url(value) if value else "MISSING"
            else:
                shown = mask(value) if value else "not set"
            lines.append(f"  {key} = {shown}")
        lines.append(f"  LANGSMITH_PROJECT = {self.langsmith_project}")
        lines.append(f"  LANGSMITH_TRACING = {self.langsmith_tracing}")
        return "\n".join(lines)

    # --- typed accessors ---------------------------------------------------

    @property
    def database_url(self) -> str:
        return self._get("DATABASE_URL") or ""

    @property
    def langsmith_api_key(self) -> str | None:
        return self._get("LANGSMITH_API_KEY")

    @property
    def google_api_key(self) -> str | None:
        return self._get("GOOGLE_API_KEY")

    @property
    def groq_api_key(self) -> str | None:
        return self._get("GROQ_API_KEY")

    @property
    def openai_api_key(self) -> str | None:
        return self._get("OPENAI_API_KEY")

    @property
    def anthropic_api_key(self) -> str | None:
        return self._get("ANTHROPIC_API_KEY")

    @property
    def langsmith_project(self) -> str:
        return self._get("LANGSMITH_PROJECT") or LANGSMITH_PROJECT_DEFAULT

    @property
    def langsmith_tracing(self) -> bool:
        raw = self._get("LANGSMITH_TRACING")
        return True if raw is None else raw.lower() in ("true", "1", "yes")

    def model_for(self, stage: str) -> str:
        env_var, default = MODEL_STAGES[stage]  # KeyError on unknown stage: intended
        return self._get(env_var) or default

    # --- public-demo hardening (deployment plan 2026-07-13) -----------------

    @property
    def page_cap_max(self) -> int:
        """Server-side ceiling on the live-run page cap; the request body can
        only lower it. Default matches the dev request default."""
        return int(self._get("PAGE_CAP_MAX") or 20)

    @property
    def checks_rate_limit_per_hour(self) -> int:
        """POST /checks per-IP hourly limit; 0 disables (dev default)."""
        return int(self._get("CHECKS_RATE_LIMIT_PER_HOUR") or 0)

    @property
    def protected_run_ids(self) -> frozenset[str]:
        """Runs that DELETE /runs must refuse (the seeded showcase data)."""
        raw = self._get("PROTECTED_RUN_IDS") or ""
        return frozenset(part.strip() for part in raw.split(",") if part.strip())

    @property
    def cors_allow_origins(self) -> tuple[str, ...]:
        """Browser origins allowed to call the API cross-origin (the Vercel
        frontend in prod). Unset/blank keeps dev behavior: local web app only."""
        raw = self._get("CORS_ALLOW_ORIGINS") or ""
        parsed = tuple(part.strip() for part in raw.split(",") if part.strip())
        return parsed or ("http://localhost:3000",)


def load_settings() -> Settings:
    """Startup path: load, verify, echo (masked). The only entry point main.py uses."""
    settings = Settings.from_env()
    settings.verify()
    return settings
