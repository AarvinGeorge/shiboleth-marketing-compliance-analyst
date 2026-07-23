"""
meta:
  purpose: Integration tests (clustering C2) for the cluster payloads on
           GET /products/{id}: the additive clusters[] array must carry the
           issue layer (kind, state, rationale, parent_cluster_id,
           member_cluster_ids for issue parents) so the UI can render
           suggested/confirmed issue groupings without new endpoints.
  contract: clusters[] is additive; flags keep cluster_id + cluster_label
            unchanged (backward compatible). Rejected parents still serialize
            (the UI filters them); their children are detached. Grouping is a
            view: PATCH state=rejected ungroups, PATCH state=suggested undoes
            the ungroup (snapshot members re-attach).
  deps: docker Postgres (skipped when down); reuses the seeded test DB
        fixture pattern from test_seed_db.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from adlign.db.models import Cluster, Flag, Material, Run
from tests.integration.test_seed_db import TEST_URL, _postgres_available, seeded_session  # noqa: F401

pytestmark = pytest.mark.skipif(
    not _postgres_available(), reason="docker Postgres not running (make db-up)"
)


def _flag(run_id: str, material_id: str, cluster_id: str, quote: str) -> Flag:
    return Flag(run_id=run_id, material_id=material_id, check_id="R-01-REQ",
                axis_a=False, axis_b=False,
                intersection_tag="unapproved_violation",
                evidence_quote=quote, location="hero", reason="no disclosure",
                confidence=0.9, state="open", cluster_id=cluster_id)


@pytest.fixture
async def client_with_issue(seeded_session):  # noqa: F811
    """Seeded DB + one run with three wording clusters; a SUGGESTED issue
    parent groups two of them, the third stays unparented."""
    run = Run(product_id="turbotax-free", mode="corpus", status="completed",
              scores={"draft": 50.0, "verified": 50.0})
    seeded_session.add(run)
    await seeded_session.flush()
    material = Material(property_id="tt-website", ref="https://x/", kind="page",
                        content_hash="h-issue", extracted_text="File free.")
    seeded_session.add(material)
    await seeded_session.flush()

    w1 = Cluster(run_id=run.id, label="Free claim wording A", kind="wording")
    w2 = Cluster(run_id=run.id, label="Free claim wording B", kind="wording")
    w3 = Cluster(run_id=run.id, label="Rate claim wording", kind="wording")
    seeded_session.add_all([w1, w2, w3])
    await seeded_session.flush()

    parent = Cluster(
        run_id=run.id, label="Free eligibility scope not disclosed",
        kind="issue", state="suggested",
        rationale="Both clusters flag the same missing eligibility disclosure.",
        member_snapshot={"member_cluster_ids": [w1.id, w2.id],
                         "signatures": ["R-01:free-claim"]},
    )
    seeded_session.add(parent)
    await seeded_session.flush()
    w1.parent_cluster_id = parent.id
    w2.parent_cluster_id = parent.id

    seeded_session.add_all([
        _flag(run.id, material.id, w1.id, "File 100% free."),
        _flag(run.id, material.id, w2.id, "File for $0."),
        _flag(run.id, material.id, w3.id, "Best rate guaranteed."),
    ])
    await seeded_session.commit()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from adlign.main import create_app

    app = create_app()
    engine = create_async_engine(TEST_URL)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, {"run": run, "parent": parent, "w1": w1, "w2": w2, "w3": w3}
    await engine.dispose()


async def test_clusters_payload_carries_issue_layer(client_with_issue):
    client, ids = client_with_issue
    r = await client.get("/products/turbotax-free")
    assert r.status_code == 200, r.text
    body = r.json()
    clusters = {c["id"]: c for c in body["clusters"]}
    assert len(clusters) == 4  # 3 wording + 1 issue parent

    parent = clusters[ids["parent"].id]
    assert parent["kind"] == "issue"
    assert parent["state"] == "suggested"
    assert parent["rationale"].startswith("Both clusters flag")
    assert parent["parent_cluster_id"] is None
    assert sorted(parent["member_cluster_ids"]) == sorted(
        [ids["w1"].id, ids["w2"].id]
    )

    child = clusters[ids["w1"].id]
    assert child["kind"] == "wording"
    assert child["state"] == "auto"
    assert child["parent_cluster_id"] == ids["parent"].id
    assert "member_cluster_ids" not in child  # wording rows stay lean

    loner = clusters[ids["w3"].id]
    assert loner["parent_cluster_id"] is None


async def test_flags_payload_unchanged_backward_compatible(client_with_issue):
    client, ids = client_with_issue
    body = (await client.get("/products/turbotax-free")).json()
    assert len(body["flags"]) == 3
    by_cluster = {f["cluster_id"] for f in body["flags"]}
    # flags still point at their WORDING clusters, never at the issue parent
    assert ids["parent"].id not in by_cluster
    f1 = next(f for f in body["flags"] if f["cluster_id"] == ids["w1"].id)
    assert f1["cluster_label"] == "Free claim wording A"


async def test_confirm_reject_restore_roundtrip_reflected_in_payload(client_with_issue):
    client, ids = client_with_issue
    pid = ids["parent"].id
    r = await client.patch(f"/clusters/{pid}/issue-state",
                           json={"state": "confirmed"})
    assert r.status_code == 200, r.text
    body = (await client.get("/products/turbotax-free")).json()
    parent = next(c for c in body["clusters"] if c["id"] == pid)
    assert parent["state"] == "confirmed"

    r = await client.patch(f"/clusters/{pid}/issue-state",
                           json={"state": "rejected"})
    assert r.status_code == 200, r.text
    body = (await client.get("/products/turbotax-free")).json()
    parent = next(c for c in body["clusters"] if c["id"] == pid)
    assert parent["state"] == "rejected"
    # reject detaches the children back to top level
    child = next(c for c in body["clusters"] if c["id"] == ids["w1"].id)
    assert child["parent_cluster_id"] is None
    # the never-again memory survives on the rejected parent
    assert sorted(parent["member_cluster_ids"]) == sorted(
        [ids["w1"].id, ids["w2"].id]
    )

    # UNDO the ungroup (grouping is a view): state=suggested re-attaches the
    # snapshot members that are still unparented.
    r = await client.patch(f"/clusters/{pid}/issue-state",
                           json={"state": "suggested"})
    assert r.status_code == 200, r.text
    body = (await client.get("/products/turbotax-free")).json()
    parent = next(c for c in body["clusters"] if c["id"] == pid)
    assert parent["state"] == "suggested"
    for key in ("w1", "w2"):
        child = next(c for c in body["clusters"] if c["id"] == ids[key].id)
        assert child["parent_cluster_id"] == pid
    # the unrelated wording cluster stays untouched
    loner = next(c for c in body["clusters"] if c["id"] == ids["w3"].id)
    assert loner["parent_cluster_id"] is None
