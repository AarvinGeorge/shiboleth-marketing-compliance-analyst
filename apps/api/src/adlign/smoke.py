"""
meta:
  purpose: M0 gate instrument. One hello-world LLM call through the per-stage
           model registry (stage: check), traced in LangSmith under the
           project from config. Run: `uv run python -m adlign.smoke`.
  contract: exits 0 and prints the model reply + LangSmith project name on
            success; nonzero with the error otherwise. No secrets printed.
  deps: langchain (init_chat_model), adlign.config.
"""

from __future__ import annotations

import sys

from langchain.chat_models import init_chat_model

from adlign.config import load_settings
from adlign.main import propagate_env


def main() -> int:
    settings = load_settings()
    propagate_env(settings)
    print("Env verified:")
    print(settings.masked_echo())

    model_string = settings.model_for("check")
    print(f"\nSmoke call via stage 'check' -> {model_string}")
    model = init_chat_model(model_string, temperature=0)
    reply = model.invoke(
        "Reply with exactly: Adlign M0 smoke test OK"
    )
    print(f"Model reply: {reply.content}")
    print(f"\nTraced in LangSmith project: {settings.langsmith_project}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
