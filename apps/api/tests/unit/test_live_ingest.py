"""
meta:
  purpose: Unit tests (first) for M6 live-ingest logic: freshness-gated fetch
           decisions (cache/dedup refinement 04 §6g), run-inventory assembly,
           and the property status outcomes feeding the 07 §2 barrier
           (fetched | needs_input | skipped). The fetcher itself is a seam —
           these tests run offline.
  contract: plan_fetches skips fresh materials; ingest_property returns
            fetched materials or needs_input on fetcher failure/time-box;
            barrier_state derives run status from property statuses.
  deps: pytest.
"""

from datetime import UTC, datetime, timedelta

from shiboleth.services.ingestion.live import (
    barrier_state,
    ingest_property,
    plan_fetches,
)


def mat(ref: str, hours_old: float) -> dict:
    return {
        "ref": ref,
        "content_hash": f"h-{ref}",
        "fetched_at": datetime.now(UTC) - timedelta(hours=hours_old),
    }


class TestPlanFetches:
    def test_fresh_material_skipped(self):
        plan = plan_fetches(["a", "b"], {"a": mat("a", 1.0)}, ttl_hours=24)
        assert plan.to_fetch == ["b"]
        assert plan.cache_hits == ["a"]

    def test_stale_material_refetched(self):
        plan = plan_fetches(["a"], {"a": mat("a", 25.0)}, ttl_hours=24)
        assert plan.to_fetch == ["a"] and plan.cache_hits == []

    def test_all_missing(self):
        plan = plan_fetches(["a", "b"], {}, ttl_hours=24)
        assert plan.to_fetch == ["a", "b"]


class TestIngestProperty:
    def test_successful_fetch(self):
        def fetcher(url):
            return f"content of {url}"

        result = ingest_property("tt-web", ["u1", "u2"], fetcher, time_box_seconds=600)
        assert result.status == "fetched"
        assert len(result.materials) == 2
        assert result.materials[0]["extracted_text"] == "content of u1"
        assert result.materials[0]["content_hash"]  # hash convention applied

    def test_fetcher_failure_yields_needs_input(self):
        def fetcher(url):
            raise ConnectionError("blocked by Meta")

        result = ingest_property("tt-ig", ["p1"], fetcher, time_box_seconds=600)
        assert result.status == "needs_input"
        assert result.materials == []
        assert "blocked" in result.detail

    def test_partial_failure_still_needs_input(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            if url == "u2":
                raise TimeoutError("slow")
            return "ok"

        result = ingest_property("tt-web", ["u1", "u2"], fetcher, time_box_seconds=600)
        assert result.status == "needs_input"
        assert len(result.materials) == 1  # keeps what it got

    def test_time_box_enforced(self):
        import time

        def slow_fetcher(url):
            time.sleep(0.05)
            return "ok"

        result = ingest_property(
            "tt-ig", [f"p{i}" for i in range(50)], slow_fetcher, time_box_seconds=0.1
        )
        assert result.status == "needs_input"
        assert "time box" in result.detail


class TestBarrier:
    def test_all_fetched_proceeds(self):
        assert barrier_state({"a": "fetched", "b": "fetched"}) == "proceed"

    def test_any_needs_input_awaits(self):
        assert barrier_state({"a": "fetched", "b": "needs_input"}) == "awaiting_input"

    def test_skipped_does_not_block(self):
        assert barrier_state({"a": "fetched", "b": "skipped"}) == "proceed"

    def test_all_skipped_or_failed_still_proceeds_with_nothing(self):
        assert barrier_state({"a": "skipped"}) == "proceed"
