"""
meta:
  purpose: N2 website fetcher — crawl4ai bound with the PROVEN config from the
           frozen snapshot-capture tool (extraction parity with the corpus is
           the whole point): raw_markdown never fit_markdown (fit prunes the
           disclosure fine print), domcontentloaded + settle delay (TurboTax
           never reaches networkidle), full-page scan, honest UA. Adds BFS
           link discovery: depth<=2, cap 20 pages, domain-scoped (01_spec §3).
  contract: crawl_website(root_url, depth=2, cap=20) -> [(url, markdown)];
            fetch_page(crawler, url, cfg) -> markdown | raises. Politeness:
            sequential fetches, small delay. Social kinds are NOT handled
            here (live.ingest_property parks them as needs_input; paste
            fallback is the first-class Meta path).
  deps: crawl4ai (Playwright chromium installed via playwright install).
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlparse

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "adlign-compliance-monitor/0.1"
)
PAGE_TIMEOUT_MS = 60_000
_MD_LINK = re.compile(r"\]\((https?://[^)\s]+)\)")


def _same_domain(url: str, root: str) -> bool:
    return urlparse(url).netloc.replace("www.", "") == urlparse(root).netloc.replace(
        "www.", ""
    )


def _discover_links(markdown: str, base_url: str, root_url: str) -> list[str]:
    seen, out = set(), []
    for match in _MD_LINK.finditer(markdown):
        url = urljoin(base_url, match.group(1).split("#")[0].rstrip("/"))
        if url and url not in seen and _same_domain(url, root_url):
            seen.add(url)
            out.append(url)
    return out


async def crawl_website(
    root_url: str, depth: int = 2, cap: int = 20, politeness_delay: float = 1.0
) -> list[tuple[str, str]]:
    """BFS from root: depth<=`depth`, at most `cap` pages, same domain only.
    Returns (url, raw_markdown) pairs; per-page failures are skipped (the
    property still counts as fetched if the root succeeded)."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    browser_config = BrowserConfig(headless=True, user_agent=USER_AGENT)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",  # networkidle never fires on TurboTax
        page_timeout=PAGE_TIMEOUT_MS,
        delay_before_return_html=3.0,
        scan_full_page=True,
        scroll_delay=0.3,
        remove_overlay_elements=True,
    )

    pages: list[tuple[str, str]] = []
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(root_url.rstrip("/"), 0)]

    async with AsyncWebCrawler(config=browser_config) as crawler:
        while queue and len(pages) < cap:
            url, level = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                result = await crawler.arun(url=url, config=run_config)
            except Exception:  # noqa: BLE001 — single-page failure never kills the crawl
                continue
            if not getattr(result, "success", False):
                if not pages:  # root itself failed -> let live.ingest park it
                    raise ConnectionError(
                        getattr(result, "error_message", "root fetch failed")
                    )
                continue
            markdown = _raw_markdown(result)
            if not markdown.strip():
                continue
            pages.append((url, markdown))
            if level < depth:
                for link in _discover_links(markdown, url, root_url):
                    if link not in visited:
                        queue.append((link, level + 1))
            await asyncio.sleep(politeness_delay)
    return pages


async def fetch_urls(
    urls: list[str], politeness_delay: float = 1.0
) -> list[tuple[str, str]]:
    """Fetch an explicit URL list (semantic-discovery path): same proven
    crawl4ai config as the BFS crawl, no link discovery. Per-page failures
    are skipped; raises ConnectionError only when EVERY page fails."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    browser_config = BrowserConfig(headless=True, user_agent=USER_AGENT)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="domcontentloaded",
        page_timeout=PAGE_TIMEOUT_MS,
        delay_before_return_html=3.0,
        scan_full_page=True,
        scroll_delay=0.3,
        remove_overlay_elements=True,
    )
    pages: list[tuple[str, str]] = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for url in urls:
            try:
                result = await crawler.arun(url=url, config=run_config)
            except Exception:  # noqa: BLE001
                continue
            if not getattr(result, "success", False):
                continue
            markdown = _raw_markdown(result)
            if markdown.strip():
                pages.append((url, markdown))
            await asyncio.sleep(politeness_delay)
    if urls and not pages:
        raise ConnectionError("all discovered pages failed to fetch")
    return pages


def _raw_markdown(result) -> str:
    """raw_markdown across crawl4ai version shapes; NEVER fit_markdown."""
    md = getattr(result, "markdown", None)
    if md is None:
        return ""
    raw = getattr(md, "raw_markdown", None)
    if isinstance(raw, str) and raw.strip():
        return raw
    return md if isinstance(md, str) else ""
