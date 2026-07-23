"""
meta:
  purpose: Unit tests (first) for N1 extract-properties — freeform text to
           typed Property drafts. The LLM seam is injected like the checker's;
           deterministic fallback parsing must catch plain URLs/handles even
           with no LLM (U3 chips must never block on a model).
  contract: extract_properties(text, invoke|None) -> [PropertyDraft];
            kinds website|instagram|facebook; dedup by normalized target.
  deps: pytest.
"""

from adlign.services.ingestion.extract import PropertyDraft, extract_properties

TEXT = """check these:
https://turbotax.intuit.com/ and also instagram.com/turbotax
plus https://www.facebook.com/turbotax and turbotax.intuit.com/personal-taxes
"""


def test_deterministic_parse_without_llm():
    drafts = extract_properties(TEXT, invoke=None)
    kinds = {(d.kind, d.url_or_handle) for d in drafts}
    assert ("website", "https://turbotax.intuit.com/") in kinds
    assert ("instagram", "instagram.com/turbotax") in kinds
    assert ("facebook", "facebook.com/turbotax") in kinds
    assert ("website", "https://turbotax.intuit.com/personal-taxes") in kinds


def test_dedup_same_target():
    drafts = extract_properties(
        "instagram.com/turbotax and https://instagram.com/turbotax", invoke=None
    )
    assert len([d for d in drafts if d.kind == "instagram"]) == 1


def test_empty_text():
    assert extract_properties("   ", invoke=None) == []


def test_llm_drafts_merged_with_parsed(monkeypatch):
    def fake_invoke(_prompt: str):
        return [PropertyDraft(kind="website", url_or_handle="https://example.com/promo")]

    drafts = extract_properties("see example.com promo page", invoke=fake_invoke)
    assert any(d.url_or_handle == "https://example.com/promo" for d in drafts)
