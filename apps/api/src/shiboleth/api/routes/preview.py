"""
meta:
  purpose: Flag page preview route (spec: docs/superpowers/specs/
           2026-07-10-flag-preview-design.md). Serves the flag's live source
           page transformed to self-highlight the evidence quote, rendered by
           the evidence panel's Preview iframe.
  contract: GET /flags/{flag_id}/preview -> text/html. 404 unknown flag,
            400 non-http(s) materials.ref, 502 upstream fetch failure.
            Accepts flag_id only (never a URL) -> no open proxy.
  deps: db models; services.preview (fetch_page TTL-cached by material id,
        build_preview_html).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from shiboleth.db.models import Flag, Material
from shiboleth.services.preview import build_preview_html, fetch_page, is_previewable_url

router = APIRouter()


@router.get("/flags/{flag_id}/preview", response_class=HTMLResponse)
async def flag_preview(flag_id: str, request: Request) -> HTMLResponse:
    async with request.app.state.session_factory() as session:
        flag = await session.get(Flag, flag_id)
        if flag is None:
            raise HTTPException(404, "flag not found")
        material = (
            await session.get(Material, flag.material_id)
            if flag.material_id
            else None
        )
        if material is None:
            raise HTTPException(404, "flag has no material")
        if not is_previewable_url(material.ref):
            raise HTTPException(400, "material ref is not a previewable URL")
        quote = flag.evidence_quote

    try:
        final_url, html = await fetch_page(material.ref, cache_key=material.id)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"live page fetch failed: {exc}") from exc

    return HTMLResponse(
        build_preview_html(html, final_url, quote),
        headers={"X-Robots-Tag": "noindex"},
    )
