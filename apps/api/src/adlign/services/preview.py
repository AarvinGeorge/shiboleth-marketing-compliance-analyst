"""
meta:
  purpose: Flag page preview service (spec: docs/superpowers/specs/
           2026-07-10-flag-preview-design.md). Fetches the live source page
           for a flag's material and transforms it so it self-highlights the
           evidence quote when rendered in the evidence-panel iframe: <base>
           injection, meta-CSP strip, vendored mark.js + highlighter script.
  contract: build_preview_html(html, final_url, quote) -> str (pure);
            is_previewable_url(url) -> bool (http/https only, SSRF guard);
            fetch_page(url) -> (final_url, html), TTL-cached by caller key.
  deps: httpx; static/mark.min.js (vendored, MIT).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

_MARK_JS = (Path(__file__).parent.parent / "api" / "static" / "mark.min.js").read_text()

# Browser UA: some marketing sites serve bot UAs a challenge page.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_FETCH_TIMEOUT_S = 10.0
_CACHE_TTL_S = 600.0

_HEAD_RE = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)
_BODY_CLOSE_RE = re.compile(r"</body\s*>", re.IGNORECASE)
_META_CSP_RE = re.compile(
    r"<meta[^>]+http-equiv\s*=\s*[\"']content-security-policy[\"'][^>]*>",
    re.IGNORECASE,
)

# Highlighter: exact match first (mark(), acrossElements covers quotes that
# span tags), then a punctuation-normalized regex pass (markRegExp): the
# extracted quote has straightened punctuation while the live DOM keeps the
# smart forms (you're vs you’re) and mark.js ignorePunctuation does NOT
# bridge that (live-verified). One delayed retry for pages that hydrate after
# load; then report found/not-found to the parent app. Mark style mirrors the
# app's danger evidence-underline token.
_HIGHLIGHTER = """
<style>
mark.adlign-evidence-mark {
  background: #fee2e2 !important;
  border-bottom: 2px solid #dc2626 !important;
  color: inherit !important;
  padding: 1px 2px;
}
</style>
<script>
(function () {
  var adlignQuote = %(quote_json)s;
  var adlignQuoteRegexSrc = %(regex_json)s;
  var CLS = "adlign-evidence-mark";
  function attemptExact(cb) {
    var found = false;
    new Mark(document.body).mark(adlignQuote, {
      separateWordSearch: false,
      acrossElements: true,
      className: CLS,
      each: function () { found = true; },
      done: function () { cb(found); }
    });
  }
  function attemptRegex(cb) {
    var found = false;
    new Mark(document.body).markRegExp(new RegExp(adlignQuoteRegexSrc, "g"), {
      className: CLS,
      each: function () { found = true; },
      done: function () { cb(found); }
    });
  }
  function scrollToMark() {
    var el = document.querySelector("mark." + CLS);
    if (el) el.scrollIntoView({ block: "center" });
  }
  function report(found) {
    try {
      parent.postMessage({ type: "adlign-preview", found: found }, "*");
    } catch (e) {}
  }
  function run(retriesLeft) {
    attemptExact(function (found) {
      if (found) { scrollToMark(); report(true); return; }
      attemptRegex(function (foundLoose) {
        if (foundLoose) { scrollToMark(); report(true); return; }
        if (retriesLeft > 0) { setTimeout(function () { run(retriesLeft - 1); }, 1500); }
        else { report(false); }
      });
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { run(1); });
  } else {
    run(1);
  }
})();
</script>
"""

# smart/straight punctuation equivalence classes for the regex pass
_CHAR_CLASSES = {
    "'": "['’‘]",
    "’": "['’‘]",
    "‘": "['’‘]",
    '"': "[\"“”]",
    "“": "[\"“”]",
    "”": "[\"“”]",
    "-": "[-–—]",
    "–": "[-–—]",
    "—": "[-–—]",
}


def _quote_regex_source(quote: str) -> str:
    """Quote -> JS regex source where straight/smart punctuation variants are
    equivalent and whitespace runs (incl. nbsp) collapse to \\s+."""
    parts: list[str] = []
    for ch in quote:
        if ch.isspace():
            if not parts or parts[-1] != r"\s+":
                parts.append(r"\s+")
        elif ch in _CHAR_CLASSES:
            parts.append(_CHAR_CLASSES[ch])
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def is_previewable_url(url: str) -> bool:
    """Only http(s) URLs are fetchable; corpus page ids and exotic schemes
    are not. The endpoint never accepts a caller-supplied URL, this guards
    whatever landed in materials.ref."""
    return bool(re.match(r"^https?://", url, re.IGNORECASE))


def build_preview_html(html: str, final_url: str, quote: str) -> str:
    """Pure transform: page HTML -> self-highlighting preview document."""
    base_tag = f'<base href="{final_url}">'
    match = _HEAD_RE.search(html)
    if match:
        insert_at = match.end()
        html = html[:insert_at] + base_tag + html[insert_at:]
    else:
        html = base_tag + html

    html = _META_CSP_RE.sub("", html)

    # json.dumps then escape "</" so a quote containing </script> cannot
    # terminate the injected script element.
    quote_json = json.dumps(quote).replace("</", "<\\/")
    regex_json = json.dumps(_quote_regex_source(quote)).replace("</", "<\\/")
    injection = f"<script>{_MARK_JS}</script>" + _HIGHLIGHTER % {
        "quote_json": quote_json,
        "regex_json": regex_json,
    }
    match = _BODY_CLOSE_RE.search(html)
    if match:
        html = html[: match.start()] + injection + html[match.start() :]
    else:
        html = html + injection
    return html


# module-level TTL cache: {key: (fetched_at_monotonic, final_url, html)}
_cache: dict[str, tuple[float, str, str]] = {}


async def fetch_page(url: str, cache_key: str | None = None) -> tuple[str, str]:
    """Fetch the live page (browser UA, redirects, 10s timeout). Returns
    (final_url, html). Raises httpx.HTTPError on network failure and
    httpx.HTTPStatusError on non-2xx. TTL-cached when cache_key is given."""
    if cache_key is not None:
        hit = _cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL_S:
            return hit[1], hit[2]
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=_FETCH_TIMEOUT_S,
        headers={"User-Agent": _UA},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    result = (str(resp.url), resp.text)
    if cache_key is not None:
        _cache[cache_key] = (time.monotonic(), result[0], result[1])
    return result
