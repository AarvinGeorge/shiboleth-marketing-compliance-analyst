# Flag page preview with auto-highlight — design (approved 2026-07-10)

## Problem

From the flag detail page an analyst can open the original source in a new tab,
but cannot see the flagged page inline, and nothing locates the violating line
on the real page. Cross-origin iframes cannot be scripted, so a plain iframe
cannot auto-scroll or highlight. Stored snapshots are markdown (no raw HTML),
so only the live page can be rendered with real fidelity.

## Decision

Backend proxy + server-side script injection ("live page, proxied"), approved
over as-checked snapshot rendering and plain iframe.

## Architecture

- `GET /flags/{flag_id}/preview` (FastAPI, read-only) →
  flag → material.ref (URL) + evidence_quote. Accepts flag_id only, never a
  URL param (no open proxy / SSRF; scheme must be http/https).
- Server fetch: httpx, browser UA, follow redirects, 10s timeout.
  In-memory TTL cache (600s) keyed by material_id holding the raw fetched HTML.
- HTML transform (pure function, unit-tested):
  1. Inject `<base href="{final_url}">` after `<head>` so relative assets load.
  2. Strip `<meta http-equiv="Content-Security-Policy">` tags (they would block
     the injected script).
  3. Inject mark.js (vendored 8.11.1 min build, static asset) + a small
     highlighter script carrying two payloads: the JSON-encoded evidence
     quote (exact mark(), acrossElements, covers quotes spanning tags) and a
     server-built normalized regex (markRegExp) where straight/smart
     punctuation variants are equivalence classes (['’‘], [-–—], ["“”]) and
     whitespace runs collapse to \s+. Live-verified necessity: the TurboTax
     DOM keeps curly apostrophes while extracted quotes are straightened, and
     mark.js ignorePunctuation does NOT bridge the two forms. One delayed
     retry for hydrating pages; highlight class styled like the app's danger
     evidence mark; scrollIntoView(center); postMessage
     {type:'shiboleth-preview', found} to the parent.
- Errors: 404 unknown flag; 502 on fetch failure/timeout/non-2xx.

## Frontend

- Evidence panel gets a `Text | Preview` toggle (shadcn Tabs; guardrail 5).
  Text = existing highlighted-quote view, default, unchanged.
- New `PagePreview` component: iframe
  `sandbox="allow-scripts allow-same-origin"` (no allow-top-navigation →
  frame-busting cannot hijack the tab), ~560px, loading skeleton until load,
  postMessage listener:
  - found=false → amber banner "page changed since this run".
  - iframe error / 15s timeout → "live page preview unavailable" banner.
- Header "View original source" button unchanged.

## Limitations (accepted)

- JS-only SPA pages may render empty server-side → banner fallback.
  Day-2: reuse crawl4ai (dependency since M6) to render such pages.
- Live page may differ from what the run checked; the banner states this.

## Testing

- Unit: transform function (base inject incl. no-head case, CSP strip,
  script + quote payload present, scheme guard).
- Integration: endpoint 200 text/html with transformed fixture HTML via
  mocked fetch; 404 unknown flag.
- E2E: Playwright — open a real flag, switch to Preview, assert the injected
  mark exists in the frame; screenshot as evidence.
