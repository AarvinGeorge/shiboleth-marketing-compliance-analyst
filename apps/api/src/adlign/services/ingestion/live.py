"""
meta:
  purpose: M6 live-ingest logic (N2 core): freshness-gated fetch planning
           (cache/dedup, 04 §6g refinement 1 — never refetch fresh content),
           per-property ingestion inside a hard time-box producing the 07 §2
           property statuses (fetched | needs_input | skipped), and the
           barrier derivation (any needs_input -> run awaits paste/skip).
  contract: pure logic; the fetcher is an injected callable (crawl4ai binds
            in crawler.py at M6 wiring; tests inject fakes). Pasted content
            re-enters through the same content-hash path.
  deps: adlign.services.scoring.formulas (hash + freshness conventions).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from adlign.services.scoring.formulas import content_hash, is_fresh


@dataclass(frozen=True)
class FetchPlan:
    to_fetch: list[str]
    cache_hits: list[str]


@dataclass
class PropertyIngest:
    property_id: str
    status: str  # fetched | needs_input | skipped
    materials: list[dict] = field(default_factory=list)
    detail: str = ""


def plan_fetches(
    refs: list[str], stored: dict[str, dict], ttl_hours: float = 24.0
) -> FetchPlan:
    """Fetch only missing or stale refs; fresh stored materials are reused."""
    to_fetch, cache_hits = [], []
    for ref in refs:
        material = stored.get(ref)
        if material is not None and is_fresh(material["fetched_at"], ttl_hours):
            cache_hits.append(ref)
        else:
            to_fetch.append(ref)
    return FetchPlan(to_fetch=to_fetch, cache_hits=cache_hits)


def ingest_property(
    property_id: str,
    refs: list[str],
    fetcher: Callable[[str], str],
    time_box_seconds: float = 600.0,
) -> PropertyIngest:
    """Fetch each ref inside the shared time-box. ANY failure or time-box
    expiry parks the property as needs_input (07 §2: paste fallback is a
    first-class path); successfully fetched materials are kept either way."""
    started = time.monotonic()
    materials: list[dict] = []
    for ref in refs:
        if time.monotonic() - started > time_box_seconds:
            return PropertyIngest(
                property_id, "needs_input", materials,
                f"time box ({time_box_seconds:.0f}s) expired after "
                f"{len(materials)}/{len(refs)} fetches",
            )
        try:
            text = fetcher(ref)
        except Exception as exc:  # noqa: BLE001 — any fetch error parks the property
            return PropertyIngest(
                property_id, "needs_input", materials,
                f"fetch failed for {ref}: {exc}",
            )
        materials.append({
            "ref": ref,
            "extracted_text": text,
            "content_hash": content_hash(text),
            "fetched_at": datetime.now(UTC),
        })
    return PropertyIngest(property_id, "fetched", materials)


def barrier_state(property_statuses: dict[str, str]) -> str:
    """07 §2 (pinned): if any property is needs_input the graph run ENDS and
    the run awaits paste/skip; skipped never blocks."""
    if any(status == "needs_input" for status in property_statuses.values()):
        return "awaiting_input"
    return "proceed"
