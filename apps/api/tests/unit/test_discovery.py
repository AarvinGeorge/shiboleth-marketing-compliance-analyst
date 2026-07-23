"""
meta:
  purpose: Unit tests for semantic page discovery (ingestion redesign
           2026-07-13): rule-relevance selection, cap semantics, root
           always first, no-sitemap fallback contract, deny filtering.
  contract: discover_urls returns [] when no sitemap (caller falls back to
            BFS); otherwise root + top-(cap-1) relevance>0 URLs. LLM ranker
            injected; CI never calls out.
  deps: pytest.
"""

import pytest

from adlign.services.ingestion import discovery


def fake_ranker(rules, batch):
    # relevance by simple content: pricing/free pages score high
    out = []
    for u in batch:
        rel = 3 if "free" in u else (2 if "pricing" in u else 0)
        out.append({"url": u, "relevance": rel})
    return out


class TestSelectTop:
    def test_orders_by_relevance_then_url_and_caps(self):
        scored = [
            {"url": "https://x.com/b-pricing", "relevance": 2},
            {"url": "https://x.com/zzz", "relevance": 0},
            {"url": "https://x.com/a-free", "relevance": 3},
        ]
        assert discovery.select_top(scored, 2) == [
            "https://x.com/a-free", "https://x.com/b-pricing"]

    def test_zero_relevance_never_selected(self):
        scored = [{"url": "https://x.com/blog", "relevance": 0}]
        assert discovery.select_top(scored, 5) == []


@pytest.mark.asyncio
async def test_discover_urls_root_first_and_capped(monkeypatch):
    async def fake_harvest(root_url):
        return [f"https://x.com/p{i}-free" for i in range(10)] + [
            "https://x.com/pricing", "https://x.com/careers"]
    monkeypatch.setattr(discovery, "harvest_sitemap_urls", fake_harvest)

    rules = [{"id": "R-01", "verbatim_text": "free rule"}]
    urls = await discovery.discover_urls("https://x.com", rules, 4, fake_ranker)
    assert urls[0] == "https://x.com"          # root always first
    assert len(urls) == 4                       # cap respected
    assert all("careers" not in u for u in urls)


class TestDiversify:
    def test_one_section_cannot_monopolize(self):
        # E2E postmortem: thousands of expert profiles listed first
        urls = ([f"https://x.com/local-tax-experts/p{i}" for i in range(500)]
                + ["https://x.com/personal-taxes/free",
                   "https://x.com/refund-advance"])
        picked = discovery.diversify(urls, 10)
        assert "https://x.com/personal-taxes/free" in picked
        assert "https://x.com/refund-advance" in picked

    def test_respects_limit_and_handles_small_input(self):
        urls = ["https://x.com/a", "https://x.com/b"]
        assert discovery.diversify(urls, 10) == urls


@pytest.mark.asyncio
async def test_discover_urls_empty_without_sitemap(monkeypatch):
    async def fake_harvest(root_url):
        return []
    monkeypatch.setattr(discovery, "harvest_sitemap_urls", fake_harvest)
    urls = await discovery.discover_urls(
        "https://nositemap.example", [{"id": "R-01", "verbatim_text": "x"}],
        5, fake_ranker)
    assert urls == []  # caller falls back to BFS crawl
