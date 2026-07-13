"""
meta:
  purpose: Integration tests (first) for GET /flags/{flag_id}/preview (spec:
           docs/superpowers/specs/2026-07-10-flag-preview-design.md): the
           endpoint resolves flag -> material.ref + evidence quote, fetches
           the live page (mocked here), and returns the transformed
           self-highlighting HTML; 404 unknown flag; 502 on fetch failure;
           400 when materials.ref is not an http(s) URL.
  contract: GET /flags/{id}/preview -> text/html with <base>, mark.js and the
            JSON-encoded quote injected.
  deps: docker Postgres (skipped when down); seeded test DB fixture pattern;
        fetch_page monkeypatched, no network.
"""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from shiboleth.db.models import Flag, Material, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)

PAGE_HTML = "<html><head><title>p</title></head><body><p>File free with TaxCo.</p></body></html>"


@pytest.fixture
async def client_with_flag(seeded_session, monkeypatch):  # noqa: F811
    """App on the seeded test DB + one flag whose material has a real URL ref."""
    run = Run(product_id="turbotax-free", mode="corpus", status="completed")
    seeded_session.add(run)
    await seeded_session.flush()
    material = Material(property_id="tt-website", ref="https://example.com/pricing",
                        kind="page", content_hash="h-preview",
                        extracted_text="File free with TaxCo.")
    bad_material = Material(property_id="tt-website", ref="P52 (footer)",
                            kind="page", content_hash="h-preview-bad",
                            extracted_text="x")
    seeded_session.add_all([material, bad_material])
    await seeded_session.flush()
    flag = Flag(run_id=run.id, material_id=material.id, check_id="R-01-REQ",
                axis_a=False, axis_b=False, intersection_tag="unapproved_violation",
                evidence_quote="File free with TaxCo.", location="hero",
                reason="no disclosure", confidence=0.9, state="open")
    bad_flag = Flag(run_id=run.id, material_id=bad_material.id, check_id="R-01-REQ",
                    axis_a=False, axis_b=False,
                    intersection_tag="unapproved_violation",
                    evidence_quote="x", location="P52 (footer)",
                    reason="r", confidence=0.9, state="open")
    seeded_session.add_all([flag, bad_flag])
    await seeded_session.commit()

    async def fake_fetch(url, cache_key=None):
        return url, PAGE_HTML

    import shiboleth.api.routes.preview as preview_route

    monkeypatch.setattr(preview_route, "fetch_page", fake_fetch)

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from shiboleth.main import create_app

    app = create_app()
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, flag, bad_flag, monkeypatch
    await engine.dispose()


async def test_preview_returns_transformed_html(client_with_flag):
    client, flag, _, _ = client_with_flag
    r = await client.get(f"/flags/{flag.id}/preview")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert '<base href="https://example.com/pricing">' in r.text
    assert "mark.js v8" in r.text
    assert '"File free with TaxCo."' in r.text  # JSON-encoded quote payload
    assert "shiboleth-preview" in r.text  # postMessage contract


async def test_preview_unknown_flag_404(client_with_flag):
    client, *_ = client_with_flag
    r = await client.get("/flags/nope/preview")
    assert r.status_code == 404


async def test_preview_non_url_ref_400(client_with_flag):
    client, _, bad_flag, _ = client_with_flag
    r = await client.get(f"/flags/{bad_flag.id}/preview")
    assert r.status_code == 400


async def test_preview_fetch_failure_502(client_with_flag):
    client, flag, _, monkeypatch = client_with_flag

    async def failing_fetch(url, cache_key=None):
        raise httpx.ConnectError("boom")

    import shiboleth.api.routes.preview as preview_route

    monkeypatch.setattr(preview_route, "fetch_page", failing_fetch)
    r = await client.get(f"/flags/{flag.id}/preview")
    assert r.status_code == 502
