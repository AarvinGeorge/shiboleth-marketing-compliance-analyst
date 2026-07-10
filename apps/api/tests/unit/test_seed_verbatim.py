"""
meta:
  purpose: Aarvin's M1 requirement: assert the seeded rule text matches doc 05
           §1 BYTE-FOR-BYTE. Re-extracts the four numbered rules from the
           canonical doc with the same regex the generator used and compares
           against seed_rules.RULES. Skips (loudly) only when doc 05 is absent
           (standalone clone); in this workspace it always runs.
  contract: any drift between seed_rules.py and doc 05 §1 fails the suite.
  deps: pytest; ../../../05_shibboleth_problem_context_and_scorecard doc.
"""

import re

import pytest

from shiboleth.config import REPO_ROOT
from shiboleth.db.seed_rules import RULES

DOC05 = REPO_ROOT.parent / "05_shibboleth_problem_context_and_scorecard_2026-07-09.md"


def extract_rules_from_doc05() -> list[str]:
    text = DOC05.read_text(encoding="utf-8")
    section1 = text.split("## 1.")[1].split("## 2.")[0]
    return re.findall(r"^\d+\.\s(.+)$", section1, flags=re.M)


needs_doc05 = pytest.mark.skipif(
    not DOC05.exists(),
    reason="doc 05 not present (standalone clone); byte-for-byte check needs the canonical doc",
)


@needs_doc05
def test_seeded_rule_text_matches_doc05_byte_for_byte():
    doc_rules = extract_rules_from_doc05()
    assert len(doc_rules) == 4
    assert len(RULES) == 4
    for (rule_id, verbatim_text, _sev, position), doc_text in zip(RULES, doc_rules):
        assert verbatim_text == doc_text, (
            f"{rule_id} drifted from doc 05 §1 (byte-for-byte check failed)"
        )
        assert position == int(rule_id[-1])


@needs_doc05
def test_rule_03_preserves_double_space_before_bank():
    # Canary for silent whitespace normalization anywhere in the chain.
    assert "through  Bank" in RULES[2][1]


def test_rule_ids_severities_positions():
    assert [r[0] for r in RULES] == ["R-01", "R-02", "R-03", "R-04"]
    # Severities per the frozen ground-truth distribution.
    assert [r[2] for r in RULES] == ["High", "High", "Medium", "Medium"]
    assert [r[3] for r in RULES] == [1, 2, 3, 4]
