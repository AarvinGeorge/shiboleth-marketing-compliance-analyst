"""
meta:
  purpose: N1 extract-properties (01_spec §4): freeform links text -> typed
           property drafts. Serves BOTH the U3 live-chips endpoint and the
           run-creation path (same function, per spec). Deterministic
           URL/handle parsing first — chips never block on a model — with an
           optional LLM pass merged in for messy prose.
  contract: extract_properties(text, invoke) -> [PropertyDraft]; kinds
            website|instagram|facebook; dedup by normalized target; invoke
            None = parse-only (also the offline/CI path).
  deps: stdlib regex; optional LLM seam (per-stage model, injected).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from pydantic import BaseModel

_URL = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})(/[^\s\"'<>)]*)?", re.I)
_SOCIAL = {"instagram.com": "instagram", "facebook.com": "facebook", "fb.com": "facebook"}


class PropertyDraft(BaseModel):
    kind: str  # website | instagram | facebook
    url_or_handle: str


def _normalize_target(kind: str, domain: str, path: str) -> str:
    path = (path or "").rstrip()
    if kind in ("instagram", "facebook"):
        handle = path.strip("/").split("/")[0] if path else ""
        return f"{domain}/{handle}" if handle else domain
    return f"https://{domain}{path or '/'}"


def extract_properties(
    text: str, invoke: Callable[[str], list[PropertyDraft]] | None = None
) -> list[PropertyDraft]:
    seen: set[str] = set()
    drafts: list[PropertyDraft] = []

    for match in _URL.finditer(text):
        domain = match.group(1).lower()
        base = ".".join(domain.split(".")[-2:])
        kind = _SOCIAL.get(base, "website")
        if kind == "facebook":
            domain = "facebook.com"
        if kind == "instagram":
            domain = "instagram.com"
        target = _normalize_target(kind, domain, match.group(2))
        key = f"{kind}:{target.lower().rstrip('/')}"
        if key in seen:
            continue
        seen.add(key)
        drafts.append(PropertyDraft(kind=kind, url_or_handle=target))

    if invoke is not None:
        try:
            for draft in invoke(text):
                key = f"{draft.kind}:{draft.url_or_handle.lower().rstrip('/')}"
                if key not in seen:
                    seen.add(key)
                    drafts.append(draft)
        except Exception:  # noqa: BLE001 — chips degrade to parse-only, never block
            pass

    return drafts
