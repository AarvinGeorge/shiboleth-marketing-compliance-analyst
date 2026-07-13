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
    "R-02": ["apr", "finance charge", "loan fee", "interest rate",
             "annual percentage rate"],
    "R-03": ["fdic", "member fdic", "insured"],
    "R-04": ["bonus", "reward", "referral", "apy", "annual percentage yield"],
}

# Broad, low-precision terms: real recall signal (GT2-V51: "rates over 6%"
# carried no primary keyword) but must never crowd primary hits out of the
# budget (GT2 iter-2 regression: bare "rate" hits displaced "0% APR" text;
# generic "checking/deposit" mentions displaced the Member-FDIC statement).
RULE_KEYWORDS_BROAD: dict[str, list[str]] = {
    "R-01": [],
    "R-02": ["rate", "rates"],
    "R-03": ["deposit", "checking", "savings"],
    "R-04": [],
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
_COMPILED_BROAD: dict[str, list[re.Pattern]] = {
    rule: [_pattern_for(k) for k in kws]
    for rule, kws in RULE_KEYWORDS_BROAD.items()
}


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _PARA_SPLIT.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def library_anchor_keywords(approved_text: str) -> list[str]:
    """Digit-bearing tokens of an approved library text ('37%', '1040',
    '$250,000') — high-precision anchors so windows never truncate away the
    very disclosure a library-linked rule judges (GT-F03 postmortem: the
    footer's drifted disclosure fell outside the capped windows)."""
    tokens = {t.strip(".,;:()[]") for t in approved_text.split()}
    return sorted({t for t in tokens if any(c.isdigit() for c in t) and len(t) >= 2})


def extract_windows(
    text: str,
    rule_id: str,
    context_paragraphs: int = 1,
    max_total_chars: int = 6000,
    extra_keywords: list[str] | None = None,
    fallback_chars: int | None = None,
) -> list[str]:
    """Keyword-anchored windows: each hit paragraph +/- context, merged when
    overlapping, VERBATIM substrings of `text`, capped at max_total_chars.
    extra_keywords (e.g. library anchors) rank FIRST so anchor-bearing
    paragraphs survive the cap.

    Budget-priority selection (GT2 baseline postmortem): a merged range that
    exceeds the remaining budget is never prefix-truncated — on nav-heavy
    pages that kept site navigation and dropped the disclosures at the
    bottom (12/21 missed violations, all retrieval). Instead the range is
    split back into its individual hit paragraphs (anchors first) and those
    are emitted until the budget fills.

    fallback_chars: when NO keyword hits at all, return [text[:fallback_chars]]
    instead of [] so the checker still sees the material (semantic-recall
    stopgap until pgvector; None preserves the historical empty-list contract).

    Windows are MATCH-CENTERED slices, not paragraph prefixes (GT2 iter-2
    postmortem: raw_markdown paragraphs run to 17k chars, so paragraph-unit
    windows let the budget die on giant low-value blocks while the match
    itself got truncated away). Every emitted window is guaranteed to
    contain the keyword text that earned it. Priority: library anchors >
    primary rule keywords > broad keywords (RULE_KEYWORDS_BROAD)."""
    anchor_patterns = [_pattern_for(k) for k in (extra_keywords or [])]
    tiers = [anchor_patterns, _COMPILED[rule_id], _COMPILED_BROAD[rule_id]]

    # per tier: first match position per paragraph (doc order within tier)
    spans = _paragraph_spans(text)
    before = max(400, context_paragraphs * 400)
    after = max(1800, context_paragraphs * 1800)
    hits: list[tuple[int, int]] = []  # (tier, match_start), deduped by para
    claimed: set[tuple[int, int]] = set()  # (tier-independent) para claims
    for tier, patterns in enumerate(tiers):
        if not patterns:
            continue
        for pi, (s, e) in enumerate(spans):
            if any((t, pi) in claimed for t in range(tier + 1)):
                continue
            para = text[s:e]
            starts = [m.start() + s for p in patterns for m in [p.search(para)] if m]
            if starts:
                claimed.add((tier, pi))
                hits.append((tier, min(starts)))
    if not hits:
        if fallback_chars and text.strip():
            return [text[:fallback_chars]]
        return []

    windows: list[str] = []
    intervals: list[tuple[int, int]] = []  # emitted char ranges
    total = 0
    for tier, m in sorted(hits, key=lambda h: (h[0], h[1])):
        remaining = max_total_chars - total
        if remaining < 200:
            break
        lo = max(0, m - before)
        hi = min(len(text), m + after)
        # clip against already-emitted ranges (never duplicate text)
        for a, b in intervals:
            if lo < b and hi > a:  # overlap
                if m >= a and m < b:  # match already covered
                    lo = hi = m  # skip entirely
                    break
                if lo < a:
                    hi = min(hi, a)
                else:
                    lo = max(lo, b)
        sliver = hi - lo < 80 and intervals  # clipped remnant, not a short doc
        if sliver or not (lo <= m < hi):
            continue
        if hi - lo > remaining:
            # shrink but keep the match inside the window
            hi = min(hi, max(m + 1, lo + remaining))
            if m >= hi:
                continue
        window = text[lo:hi]
        if not window.strip():
            continue
        windows.append(window)
        intervals.append((lo, hi))
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
