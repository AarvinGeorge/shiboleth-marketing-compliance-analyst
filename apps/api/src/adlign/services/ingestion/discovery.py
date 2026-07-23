"""
meta:
  purpose: Semantic page discovery for live checks (roadmap increment 4,
           pulled forward 2026-07-13): instead of blind BFS depth-crawling,
           harvest the medium's sitemaps and have an LLM score every URL's
           relevance to the MEANING of the live scorecard rules (DB-driven,
           so custom rules steer discovery), then return the top page-cap
           URLs. Same mechanism that built ground truth v2.
  contract: discover_urls(root_url, rules, cap, ranker) -> list[str] (<=cap,
            root always included first). ranker is injected (tests use
            fakes). No sitemap found -> [] (caller falls back to BFS crawl).
  deps: httpx (sitemap fetch), pydantic; langchain for production_ranker.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from urllib.parse import urlparse

from pydantic import BaseModel, Field

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_DENY_SUBSTR = ("/search", "/login", "/sign-in", "javascript:", ".pdf",
                ".svg", ".png", ".jpg", ".css", ".js", "/account")
_MAX_RANKED = 1200  # sanity cap on LLM ranking volume per check
_BATCH = 60


class UrlScore(BaseModel):
    url: str
    relevance: int = Field(ge=0, le=3, description="0-3: how likely this URL's page contains language ANY scorecard rule governs.")


class UrlRanking(BaseModel):
    scores: list[UrlScore]


async def harvest_sitemap_urls(root_url: str) -> list[str]:
    """Fetch /sitemap.xml (and one level of sitemap indexes) for the root's
    host. Returns deduped same-host URLs; [] when no sitemap exists."""
    import httpx

    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls: list[str] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=30,
                                 headers={"User-Agent": "adlign-compliance-monitor/0.1"}) as client:
        queue = [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"]
        seen_maps: set[str] = set()
        while queue:
            sm = queue.pop(0)
            if sm in seen_maps:
                continue
            seen_maps.add(sm)
            try:
                resp = await client.get(sm)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
            except Exception:  # noqa: BLE001 — missing sitemap is normal
                continue
            tag = root.tag.split("}")[-1]
            locs = [loc.text.strip() for loc in root.findall(".//sm:loc", _NS)
                    if loc.text]
            if tag == "sitemapindex":
                queue.extend(locs[:50])
            else:
                urls.extend(locs)
    host = parsed.netloc.replace("www.", "")
    out, seen = [], set()
    for u in urls:
        u = u.rstrip("/")
        if (urlparse(u).netloc.replace("www.", "") == host
                and u not in seen
                and not any(s in u.lower() for s in _DENY_SUBSTR)):
            seen.add(u)
            out.append(u)
    return out


def diversify(urls: list[str], limit: int) -> list[str]:
    """Round-robin across first-path-segment sections so one URL pattern
    can never monopolize the ranking budget (E2E postmortem 2026-07-13:
    TurboTax's sitemap lists thousands of /local-tax-experts/* profiles
    alphabetically first; a naive prefix slice ranked ONLY those and
    discovery returned nothing)."""
    from collections import OrderedDict, deque

    buckets: OrderedDict[str, deque] = OrderedDict()
    for u in urls:
        seg = urlparse(u).path.strip("/").split("/")[0] or "_root"
        buckets.setdefault(seg, deque()).append(u)
    out: list[str] = []
    while len(out) < min(limit, len(urls)):
        progressed = False
        for q in buckets.values():
            if q:
                out.append(q.popleft())
                progressed = True
                if len(out) >= limit:
                    break
        if not progressed:
            break
    return out


def select_top(scored: list[dict], cap: int) -> list[str]:
    ranked = sorted(scored, key=lambda s: (-s["relevance"], s["url"]))
    return [s["url"] for s in ranked if s["relevance"] > 0][:cap]


async def discover_urls(
    root_url: str, rules: list[dict], cap: int,
    ranker: Callable[[list[dict], list[str]], list[dict]],
) -> list[str]:
    """Semantic discovery: sitemap harvest -> rule-relevance ranking ->
    top-cap URLs (root prepended). [] when the site has no sitemap."""
    urls = await harvest_sitemap_urls(root_url)
    if not urls:
        return []
    urls = diversify(urls, _MAX_RANKED)
    scored: list[dict] = []
    for i in range(0, len(urls), _BATCH):
        scored.extend(ranker(rules, urls[i:i + _BATCH]))
    chosen = select_top(scored, max(1, cap - 1))
    root = root_url.rstrip("/")
    return [root] + [u for u in chosen if u != root]


def production_ranker(model_string: str) -> Callable[[list[dict], list[str]], list[dict]]:
    from langchain.chat_models import init_chat_model
    bound = init_chat_model(model_string, temperature=0, timeout=90,
                            max_retries=2, max_tokens=16_000
                            ).with_structured_output(UrlRanking)

    def rank(rules: list[dict], batch: list[str]) -> list[dict]:
        rule_block = "\n".join(
            f"{r['id']}: {r['verbatim_text']}" for r in rules)
        result = bound.invoke([
            {"role": "system", "content": (
                "You select marketing pages worth auditing against a "
                "compliance scorecard. From each URL's path alone, score "
                "0-3 how likely the page contains language ANY of these "
                "rules governs. Think about what each rule GOVERNS "
                "semantically, not keywords.\n\nScorecard (verbatim):\n"
                + rule_block)},
            {"role": "user", "content":
                "Score every URL, one entry per URL:\n" + "\n".join(batch)},
        ])
        return [{"url": s.url, "relevance": s.relevance}
                for s in result.scores]
    return rank
