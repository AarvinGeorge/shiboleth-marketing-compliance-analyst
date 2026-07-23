"""
meta:
  purpose: Recorded-LLM cassette layer for deterministic CI (guardrail 6).
           Wraps a checker invoke callable: cache key = sha256 of
           model_string + prompt; value = CheckerVerdict JSON.
  contract: CASSETTE_MODE env: replay (default; missing key = hard fail so CI
            never silently calls a paid API) | record (call through on miss,
            persist) | live (always call, never persist).
  deps: adlign.pipeline.nodes.check.CheckerVerdict; stdlib json.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

from adlign.pipeline.nodes.check import CheckerVerdict


class CassetteMiss(RuntimeError):
    """Replay mode hit a prompt with no recording (CI must never call out)."""


def cassette_invoke(
    cassette_path: Path,
    model_string: str,
    live_invoke: Callable[[str], CheckerVerdict] | None,
) -> Callable[[str], CheckerVerdict]:
    mode = os.environ.get("CASSETTE_MODE", "replay")
    recordings: dict[str, dict] = {}
    if cassette_path.exists():
        recordings = json.loads(cassette_path.read_text(encoding="utf-8"))

    def key_for(prompt: str) -> str:
        return hashlib.sha256(f"{model_string}\n{prompt}".encode()).hexdigest()

    def invoke(prompt: str) -> CheckerVerdict:
        key = key_for(prompt)
        if mode != "live" and key in recordings:
            return CheckerVerdict.model_validate(recordings[key]["verdict"])
        if mode == "replay":
            raise CassetteMiss(
                f"no recording for prompt {key[:12]}… in {cassette_path.name}; "
                "run once with CASSETTE_MODE=record"
            )
        if live_invoke is None:
            raise CassetteMiss("live call requested but no live_invoke bound")
        verdict = live_invoke(prompt)
        if mode == "record":
            recordings[key] = {
                "model": model_string,
                "prompt_preview": prompt[:160],
                "verdict": verdict.model_dump(),
            }
            cassette_path.parent.mkdir(parents=True, exist_ok=True)
            cassette_path.write_text(
                json.dumps(recordings, indent=1, sort_keys=True), encoding="utf-8"
            )
        return verdict

    return invoke
