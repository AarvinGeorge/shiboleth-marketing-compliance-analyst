"""
meta:
  purpose: Rule-relevant retrieval windowing + shared-block (footer) detection.
           PRODUCTION N4 preprocessing — used identically in corpus and live
           modes (binding condition, Aarvin 2026-07-10). Purpose: token diet
           (checker sees keyword-anchored excerpts, not 10k-word pages) and
           judged-once inheritance for boilerplate shared across pages.
  contract: extract_windows(text, rule_id) -> verbatim excerpt list (substring
            guarantee: evidence validation depends on it); empty = no trigger
            signal (checker may shortcut to not_applicable).
            detect_shared_block(pages, min_pages) -> shared paragraphs in
            stable order; strip_shared(page, shared) -> page minus shared.
  limitation: keyword recall — a violation phrased without any family keyword
            is invisible to the checker (false not_applicable). Day-2 upgrade:
            pgvector semantic retrieval (logged in code/CLAUDE.md backlog).
  deps: stdlib only.
"""

from __future__ import annotations

import re
from collections import Counter

# Keyword families per rule (mirrors the snapshot-manifest trigger families;
# case-insensitive, word-boundary anchored except symbol tokens like "$0").
RULE_KEYWORDS: dict[str, list[str]] = {
    "R-01": ["free", "$0", "no cost", "sin costo", "gratis"],
    "R-02": ["apr", "finance charge", "loan fee", "interest rate", "annual percentage rate"],
    "R-03": ["fdic", "deposit", "checking", "savings", "insured", "member fdic"],
    "R-04": ["bonus", "reward", "referral", "apy", "annual percentage yield"],
}

_PARA_SPLIT = re.compile(r"\n\s*\n")
_WS = re.compile(r"\s+")


def _pattern_for(keyword: str) -> re.Pattern:
    escaped = re.escape(keyword)
    if keyword[0].isalnum():
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


_COMPILED: dict[str, list[re.Pattern]] = {
    rule: [_pattern_for(k) for k in kws] for rule, kws in RULE_KEYWORDS.items()
}


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _PARA_SPLIT.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def extract_windows(
    text: str,
    rule_id: str,
    context_paragraphs: int = 1,
    max_total_chars: int = 6000,
) -> list[str]:
    """Keyword-anchored windows: each hit paragraph +/- context, merged when
    overlapping, VERBATIM substrings of `text`, capped at max_total_chars."""
    patterns = _COMPILED[rule_id]
    spans = _paragraph_spans(text)
    hits = [
        i
        for i, (s, e) in enumerate(spans)
        if any(p.search(text[s:e]) for p in patterns)
    ]
    if not hits:
        return []

    # expand each hit by context paragraphs, then merge overlapping ranges
    ranges: list[list[int]] = []
    for i in hits:
        lo = max(0, i - context_paragraphs)
        hi = min(len(spans) - 1, i + context_paragraphs)
        if ranges and lo <= ranges[-1][1] + 1:
            ranges[-1][1] = max(ranges[-1][1], hi)
        else:
            ranges.append([lo, hi])

    windows, total = [], 0
    for lo, hi in ranges:
        window = text[spans[lo][0] : spans[hi][1]]
        if total + len(window) > max_total_chars:
            window = window[: max_total_chars - total]
            if window:
                windows.append(window)
            break
        windows.append(window)
        total += len(window)
    return windows


def _norm_para(paragraph: str) -> str:
    return _WS.sub(" ", paragraph).strip()


def detect_shared_block(pages: list[str], min_pages: int = 20) -> list[str]:
    """Paragraphs (normalized) appearing on >= min_pages pages, returned in
    the order they appear on the first page containing them. This is the
    judged-once boilerplate block (the TurboTax footer pattern)."""
    counts: Counter[str] = Counter()
    for page in pages:
        seen = {_norm_para(p) for p in _PARA_SPLIT.split(page) if p.strip()}
        counts.update(seen)
    shared = {p for p, c in counts.items() if c >= min_pages}
    ordered: list[str] = []
    for page in pages:
        for para in _PARA_SPLIT.split(page):
            norm = _norm_para(para)
            if norm in shared and norm not in ordered:
                ordered.append(norm)
    return ordered


def strip_shared(page: str, shared: list[str]) -> str:
    """Remove shared paragraphs from a page body (normalized comparison),
    preserving everything else verbatim."""
    shared_set = set(shared)
    kept = [
        para
        for para in _PARA_SPLIT.split(page)
        if para.strip() and _norm_para(para) not in shared_set
    ]
    return "\n\n".join(kept)


def page_has_shared_block(page: str, shared: list[str], threshold: float = 0.5) -> bool:
    """Does this page carry the shared block (inherit its judgments)?"""
    if not shared:
        return False
    page_paras = {_norm_para(p) for p in _PARA_SPLIT.split(page) if p.strip()}
    present = sum(1 for s in shared if s in page_paras)
    return present / len(shared) >= threshold
