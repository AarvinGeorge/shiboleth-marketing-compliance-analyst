"""
meta:
  purpose: Unit tests for the preview HTML transform (flag page preview spec,
           docs/superpowers/specs/2026-07-10-flag-preview-design.md). Pure
           function: (html, final_url, quote) -> proxied HTML with <base>,
           meta-CSP stripped, mark.js + highlighter injected.
  contract: build_preview_html and is_previewable_url in
            adlign.services.preview.
  deps: none beyond the module under test.
"""

from __future__ import annotations

from adlign.services.preview import (
    _quote_regex_source,
    build_preview_html,
    is_previewable_url,
)

URL = "https://example.com/pricing/"
QUOTE = "File 100% free with TaxCo."


def test_base_tag_injected_after_head():
    html = "<html><head><title>t</title></head><body>hi</body></html>"
    out = build_preview_html(html, URL, QUOTE)
    head_idx = out.lower().index("<head>")
    base_idx = out.index(f'<base href="{URL}">')
    assert base_idx > head_idx
    assert base_idx < out.index("<title>")  # first child of head


def test_base_tag_injected_when_head_has_attributes():
    html = '<html><head data-x="1"><title>t</title></head><body>b</body></html>'
    out = build_preview_html(html, URL, QUOTE)
    assert f'<base href="{URL}">' in out
    assert out.index("<base") < out.index("<title>")


def test_base_tag_prepended_when_no_head():
    html = "<p>bare fragment</p>"
    out = build_preview_html(html, URL, QUOTE)
    assert out.startswith(f'<base href="{URL}">')


def test_meta_csp_stripped_case_insensitive():
    html = (
        "<html><head>"
        '<meta http-equiv="Content-Security-Policy" content="default-src none">'
        "<meta HTTP-EQUIV='content-security-policy' CONTENT='script-src none'>"
        '<meta name="viewport" content="width=device-width">'
        "</head><body>b</body></html>"
    )
    out = build_preview_html(html, URL, QUOTE)
    assert "Content-Security-Policy" not in out
    assert "content-security-policy" not in out
    assert "viewport" in out  # other meta tags untouched


def test_markjs_and_highlighter_injected_before_body_close():
    html = "<html><head></head><body><p>content</p></body></html>"
    out = build_preview_html(html, URL, QUOTE)
    assert "mark.js v8" in out  # vendored payload present
    assert "adlign-evidence-mark" in out  # highlight class
    assert '"File 100% free with TaxCo."' in out  # JSON-encoded quote
    # injected before </body>, after the page content
    assert out.index("<p>content</p>") < out.index("adlign-evidence-mark")
    assert out.rindex("</body>") > out.index("adlign-evidence-mark")


def test_injection_appended_when_no_body_close():
    html = "<p>fragment only</p>"
    out = build_preview_html(html, URL, QUOTE)
    assert "adlign-evidence-mark" in out


def test_quote_json_is_script_safe():
    # a quote containing </script> must not break out of the injected script
    quote = 'bad </script><script>alert(1)</script> quote'
    out = build_preview_html("<body>x</body>", URL, quote)
    payload_start = out.index("adlignQuote")
    assert "</script><script>alert" not in out[payload_start:]
    assert "<\\/script>" in out  # escaped form present instead


def test_postmessage_contract_present():
    out = build_preview_html("<body>x</body>", URL, QUOTE)
    assert "adlign-preview" in out  # message type the web app listens for
    assert "postMessage" in out


def test_quote_regex_normalizes_smart_punctuation():
    # regression (live-verified on the TurboTax blog): the DOM keeps curly
    # apostrophes (you’re) while the extracted quote has straight ones, and
    # mark.js ignorePunctuation does NOT bridge the two forms. The server
    # builds a character-class regex instead; both forms must match it.
    import re as _re

    src = _quote_regex_source("If you're carrying a balance at 20-25% APR.")
    assert _re.search(src, "If you’re carrying a balance at 20–25% APR.")
    assert _re.search(src, "If you're carrying a balance at 20-25% APR.")
    # whitespace runs (incl. nbsp) collapse to \s+
    assert _re.search(src, "If you’re carrying  a balance at 20—25% APR.")
    assert not _re.search(src, "totally different text")


def test_quote_regex_escapes_regex_metachars():
    src = _quote_regex_source("costs $0 (really?) [yes] 100%")
    import re as _re

    assert _re.search(src, "costs $0 (really?) [yes] 100%")
    assert not _re.search(src, "costs X0 really yes 100Z")


def test_highlighter_uses_regex_payload():
    out = build_preview_html("<body>x</body>", URL, "you're at 20-25%")
    assert "markRegExp" in out
    # json.dumps ascii-escapes the curly variants inside the char classes
    assert "\\u2019" in out  # ’ alternative for the straight apostrophe
    assert "\\u2013" in out  # – alternative for the hyphen


def test_is_previewable_url():
    assert is_previewable_url("https://example.com/a")
    assert is_previewable_url("http://example.com/a")
    assert not is_previewable_url("ftp://example.com/a")
    assert not is_previewable_url("file:///etc/passwd")
    assert not is_previewable_url("javascript:alert(1)")
    assert not is_previewable_url("P52 (footer)")  # corpus page id, not a URL
