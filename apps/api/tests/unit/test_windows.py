"""
meta:
  purpose: Unit tests (written first) for rule-relevant retrieval windowing +
           shared-footer detection — PRODUCTION N4 preprocessing, used
           identically in corpus and live modes (binding condition, Aarvin
           2026-07-10). Keyword recall limitation logged; pgvector is day-2.
  contract: extract_windows returns keyword-anchored excerpts (verbatim
            substrings of the source, merged, capped); no hits -> empty list.
            detect_shared_block finds paragraphs common to >= min_pages pages;
            strip_shared removes them from a page body.
  deps: pytest.
"""

from shiboleth.services.ingestion.windows import (
    RULE_KEYWORDS,
    detect_shared_block,
    extract_windows,
    strip_shared,
)

FREE_PAGE = """# TaxCo homepage

File your taxes with confidence.

Start for $0 with TaxCo Free Edition. Simple returns only.

Our experts have decades of experience helping filers.

Pricing subject to change without notice.
"""


class TestExtractWindows:
    def test_hit_returns_surrounding_context_verbatim(self):
        windows = extract_windows(FREE_PAGE, "R-01")
        assert windows, "free-family keywords must hit"
        joined = "\n".join(windows)
        assert "TaxCo Free Edition" in joined
        # windows are verbatim substrings (evidence validation depends on it)
        for w in windows:
            assert w in FREE_PAGE

    def test_no_hits_returns_empty(self):
        assert extract_windows("Our experts help you all year round.", "R-03") == []

    def test_all_four_rules_have_keyword_families(self):
        assert set(RULE_KEYWORDS) == {"R-01", "R-02", "R-03", "R-04"}

    def test_windows_capped(self):
        big = ("free filing offer. " + "x" * 400 + "\n\n") * 100
        windows = extract_windows(big, "R-01", max_total_chars=6000)
        assert sum(len(w) for w in windows) <= 6000

    def test_apr_family_word_boundary(self):
        # "capricious" must not trigger the APR family
        assert extract_windows("A capricious pricing scheme.", "R-02") == []
        assert extract_windows("0% APR on this loan.", "R-02") != []

    def test_bare_rate_triggers_r02(self):
        # GT2-V51 postmortem: "rates over 6%" carried no R-02 family keyword,
        # so the checker was never called on a stated finance charge
        assert extract_windows("Private loans have rates from 6-12%.", "R-02") != []
        assert extract_windows("This loan has a rate of 5.9%.", "R-02") != []

    def test_cap_keeps_hit_paragraphs_not_page_prefix(self):
        # GT2 baseline postmortem: on nav-heavy pages every paragraph hits,
        # the ranges merge into one mega-range, and prefix truncation kept
        # site navigation while dropping the disclosure at the bottom.
        nav = "\n\n".join(f"free nav link {i} " + "x" * 300 for i in range(30))
        disclosure = "Roughly 37% of taxpayers qualify for Free Edition 1040."
        page = nav + "\n\n" + disclosure
        windows = extract_windows(
            page, "R-01", max_total_chars=3000, extra_keywords=["37%", "1040"])
        joined = "\n".join(windows)
        assert disclosure in joined, "anchor paragraph must survive the cap"
        assert sum(len(w) for w in windows) <= 3000
        for w in windows:
            assert w in page  # substring guarantee holds

    def test_fallback_full_text_when_no_hits(self):
        text = "Our experts help you all year round."
        assert extract_windows(text, "R-03") == []
        assert extract_windows(text, "R-03", fallback_chars=100) == [text]
        long_text = "y" * 50_000
        fb = extract_windows(long_text, "R-03", fallback_chars=24_000)
        assert fb == [long_text[:24_000]]


PAGES = [
    f"# Page {i}\n\nUnique hero copy {i}.\n\nShared footnote: ~37% disclosure text here.\n\nShared legal block line two."
    for i in range(10)
] + ["# Odd page\n\nCompletely unique content, no shared block."]


class TestSharedBlock:
    def test_detects_paragraphs_common_to_min_pages(self):
        shared = detect_shared_block(PAGES, min_pages=8)
        assert "Shared footnote: ~37% disclosure text here." in shared
        assert "Shared legal block line two." in shared
        assert "Unique hero copy 3." not in shared

    def test_strip_shared_removes_only_shared(self):
        shared = detect_shared_block(PAGES, min_pages=8)
        stripped = strip_shared(PAGES[3], shared)
        assert "Unique hero copy 3." in stripped
        assert "Shared footnote" not in stripped

    def test_page_without_block_untouched(self):
        shared = detect_shared_block(PAGES, min_pages=8)
        assert "Completely unique content" in strip_shared(PAGES[-1], shared)

    def test_no_shared_block_when_pages_differ(self):
        assert detect_shared_block(["a\n\nb", "c\n\nd", "e\n\nf"], min_pages=2) == []


class TestEvidenceNormalization:
    def test_markdown_emphasis_tolerated(self):
        from shiboleth.pipeline.nodes.check import evidence_in_material

        material = "**TurboTax Free Edition:** TurboTax Free Edition ($0 Federal + $0 State) is available."
        quote = "TurboTax Free Edition: TurboTax Free Edition ($0 Federal + $0 State) is available."
        assert evidence_in_material(quote, material)

    def test_real_mismatch_still_fails(self):
        from shiboleth.pipeline.nodes.check import evidence_in_material

        assert not evidence_in_material("Roughly 37% of taxpayers", "~37% of filers qualify")

    def test_markdown_link_unwrapped_for_comparison(self):
        from shiboleth.pipeline.nodes.check import evidence_in_material

        material = "~37% of filers qualify. [Simple Form 1040 returns only](https://x.co/m) (no schedules)."
        quote = "~37% of filers qualify. Simple Form 1040 returns only (no schedules)."
        assert evidence_in_material(quote, material)

    def test_wording_drift_still_detected_despite_links(self):
        from shiboleth.pipeline.nodes.check import evidence_in_material

        material = "Roughly 37% of taxpayers qualify. [Simple Form 1040](https://x.co) only."
        assert not evidence_in_material("~37% of filers qualify.", material)
