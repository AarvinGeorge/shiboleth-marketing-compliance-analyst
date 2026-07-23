"""
meta:
  purpose: Endpoint tests (first) for demo hardening on the run routes:
           DELETE /runs/{id} returns 403 for PROTECTED_RUN_IDS before any DB
           work; POST /checks returns 429 past CHECKS_RATE_LIMIT_PER_HOUR
           (per client IP, X-Forwarded-For aware behind Caddy); the live-run
           page cap is clamped server-side to PAGE_CAP_MAX regardless of the
           request body. Pipeline stubbed; no Postgres needed.
  contract: 403 detail names the run as protected; 429 detail says rate
            limited; clamp passes min(requested, PAGE_CAP_MAX) into
            start_live_run(cap=...).
  deps: pytest, httpx ASGITransport; adlign.main.create_app.
"""


import pytest
from httpx import ASGITransport, AsyncClient

from adlign.main import create_app
from tests.unit.test_config import make_settings


class FakeSession:
    """Async-context session that reports 'no such row' for any get()."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return None


def make_client(settings, client_ip="203.0.113.7") -> AsyncClient:
    app = create_app()
    app.state.settings = settings
    app.state.session_factory = FakeSession
    transport = ASGITransport(app=app, client=(client_ip, 51234))
    return AsyncClient(transport=transport, base_url="http://test")


class TestProtectedRuns:
    @pytest.mark.asyncio
    async def test_protected_run_delete_is_403(self):
        settings = make_settings(PROTECTED_RUN_IDS="showcase1,showcase2")
        async with make_client(settings) as client:
            res = await client.delete("/runs/showcase1")
        assert res.status_code == 403
        assert "protected" in res.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_unprotected_run_still_reaches_the_db_path(self):
        settings = make_settings(PROTECTED_RUN_IDS="showcase1")
        async with make_client(settings) as client:
            res = await client.delete("/runs/other-run")
        assert res.status_code == 404  # FakeSession: row not found

    @pytest.mark.asyncio
    async def test_no_protection_by_default(self):
        async with make_client(make_settings()) as client:
            res = await client.delete("/runs/showcase1")
        assert res.status_code == 404


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Stub every import POST /checks resolves at call time; capture caps."""
    captured: dict = {}

    import adlign.api.routes.runs as runs_module
    import adlign.pipeline.corpus_run as corpus_run
    import adlign.pipeline.live_run as live_run
    import adlign.services.ingestion.discovery as discovery

    monkeypatch.setattr(runs_module, "_pipeline_deps", lambda settings: (None, None))

    async def fake_run_corpus(session, invoke, labeler, product_id):
        return "corpus-run-id"

    async def fake_create_live_run(session, product_id):
        return "live-run-id"

    async def fake_start_live_run(session, invoke, labeler, *, product_id,
                                  run_id, cap, ranker):
        captured["cap"] = cap

    async def fake_auto_group(app, run_id):
        return None

    monkeypatch.setattr(corpus_run, "run_corpus", fake_run_corpus)
    monkeypatch.setattr(live_run, "create_live_run", fake_create_live_run)
    monkeypatch.setattr(live_run, "start_live_run", fake_start_live_run)
    monkeypatch.setattr(discovery, "production_ranker", lambda model: None)
    monkeypatch.setattr(runs_module, "_auto_group", fake_auto_group)
    return captured


async def drain_background_tasks(client: AsyncClient) -> None:
    app = client._transport.app  # noqa: SLF001 — test-only reach-in
    for task in list(getattr(app.state, "live_tasks", ())):
        await task


class TestChecksRateLimit:
    @pytest.mark.asyncio
    async def test_over_limit_is_429(self, stub_pipeline):
        settings = make_settings(CHECKS_RATE_LIMIT_PER_HOUR="2")
        body = {"product_id": "turbotax-free", "mode": "corpus"}
        async with make_client(settings) as client:
            first = await client.post("/checks", json=body)
            second = await client.post("/checks", json=body)
            third = await client.post("/checks", json=body)
            await drain_background_tasks(client)
        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert "rate" in third.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_x_forwarded_for_distinguishes_clients(self, stub_pipeline):
        settings = make_settings(CHECKS_RATE_LIMIT_PER_HOUR="1")
        body = {"product_id": "turbotax-free", "mode": "corpus"}
        async with make_client(settings) as client:
            a1 = await client.post("/checks", json=body,
                                   headers={"X-Forwarded-For": "198.51.100.1"})
            a2 = await client.post("/checks", json=body,
                                   headers={"X-Forwarded-For": "198.51.100.1"})
            b1 = await client.post("/checks", json=body,
                                   headers={"X-Forwarded-For": "198.51.100.2"})
            await drain_background_tasks(client)
        assert a1.status_code == 200
        assert a2.status_code == 429
        assert b1.status_code == 200

    @pytest.mark.asyncio
    async def test_disabled_by_default(self, stub_pipeline):
        body = {"product_id": "turbotax-free", "mode": "corpus"}
        async with make_client(make_settings()) as client:
            responses = [await client.post("/checks", json=body) for _ in range(5)]
            await drain_background_tasks(client)
        assert all(r.status_code == 200 for r in responses)


class TestPageCapClamp:
    @pytest.mark.asyncio
    async def test_live_cap_clamped_to_page_cap_max(self, stub_pipeline):
        settings = make_settings(PAGE_CAP_MAX="8")
        body = {"product_id": "turbotax-free", "mode": "live", "page_cap": 20}
        async with make_client(settings) as client:
            res = await client.post("/checks", json=body)
            await drain_background_tasks(client)
        assert res.status_code == 200
        assert stub_pipeline["cap"] == 8

    @pytest.mark.asyncio
    async def test_live_cap_below_max_is_kept(self, stub_pipeline):
        settings = make_settings(PAGE_CAP_MAX="8")
        body = {"product_id": "turbotax-free", "mode": "live", "page_cap": 3}
        async with make_client(settings) as client:
            res = await client.post("/checks", json=body)
            await drain_background_tasks(client)
        assert res.status_code == 200
        assert stub_pipeline["cap"] == 3
