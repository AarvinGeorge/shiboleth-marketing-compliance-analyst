"""
meta:
  purpose: Scorecard decomposition (customize layer): turn a rule's VERBATIM
           text into the binary trigger/requirement checks the checker
           harness runs, plus the retrieval keyword families a new rule
           needs (without them, windowing has nothing to anchor on).
  contract: decompose(rule_text) via an injected callable -> Decomposition
            (trigger/requirement texts + evidence criteria + primary/broad
            keywords). The rule's verbatim text is NEVER altered — it is
            quoted into the prompt and stored untouched; decomposition is
            derived, editable runtime data (v1 precedent: R-02/R-03 changes
            were seed edits, logged). production_decomposer uses the
            "decompose" model stage, structured output, temperature 0.
  deps: pydantic; langchain (production callable only).
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field


class Decomposition(BaseModel):
    trigger_text: str = Field(description="Binary question: does the rule's IF-condition apply to this material at all? Phrase product-agnostically.")
    trigger_criteria: str = Field(description="Evidence criteria for the trigger: what to quote, what does NOT trigger (carry any exemptions the rule text states).")
    requirement_text: str = Field(description="Binary question: if triggered, is the rule's requirement satisfied?")
    requirement_criteria: str = Field(description="Evidence criteria for the requirement: what compliant evidence looks like, what to quote, when to mark ambiguous instead of failing.")
    primary_keywords: list[str] = Field(description="3-8 high-precision retrieval terms whose presence strongly signals the rule could apply (e.g. 'apr', 'member fdic'). Lowercase.")
    broad_keywords: list[str] = Field(description="0-5 low-precision recall terms that might signal applicability but are common words (e.g. 'rate'). Lowercase. Empty if none needed.")


_SYSTEM = (
    "You decompose marketing-compliance scorecard rules into the binary "
    "check protocol used by an automated checker: one TRIGGER question "
    "(does the rule apply?) and one REQUIREMENT question (is it "
    "satisfied?), each with evidence criteria. Rules follow an IF-THEN "
    "shape. Preserve any exemptions the rule text states (e.g. 'general "
    "statements do not trigger') inside the trigger criteria. An "
    "untriggered rule is always not-applicable, never pass. Phrase "
    "everything product-agnostically: the decomposition must work for any "
    "brand. Also derive retrieval keywords: primary = high-precision terms "
    "that anchor text excerpts for the checker; broad = recall-only common "
    "terms that must never displace primary ones."
)


def production_decomposer(model_string: str) -> Callable[[str], Decomposition]:
    from langchain.chat_models import init_chat_model
    bound = init_chat_model(model_string, temperature=0, timeout=60,
                            max_retries=2).with_structured_output(Decomposition)

    def decompose(rule_text: str) -> Decomposition:
        return bound.invoke([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content":
                f"Scorecard rule (verbatim, do not alter it):\n{rule_text}"},
        ])
    return decompose
