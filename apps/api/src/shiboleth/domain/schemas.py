"""
meta:
  purpose: The cross-cutting Pydantic contracts from 07_architecture §6.
           Frontend types in apps/web/src/lib/types.ts mirror these 1:1; if a
           field changes, both sides change in the same commit (pinned rule).
  contract: Schemas only, no logic. Full field lists derive from 01_spec §5.
            Enums are the single vocabulary for verdicts, lifecycle, events.
            Changes here are contract changes: surface to Aarvin first
            (autonomy dial, 07 §7).
  deps: pydantic v2.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- vocabulary ------------------------------------------------------------

class PropertyKind(StrEnum):
    website = "website"
    instagram = "instagram"
    facebook = "facebook"


class CheckKind(StrEnum):
    trigger = "trigger"
    requirement = "requirement"


class Severity(StrEnum):
    high = "High"
    medium = "Medium"
    low = "Low"


class IntersectionTag(StrEnum):
    """07 §6: derived solely in scoring/formulas.py from the axis pair."""
    all_good = "all_good"
    drifted_but_compliant = "drifted_but_compliant"
    approved_but_non_compliant = "approved_but_non_compliant"
    unapproved_violation = "unapproved_violation"


class FlagState(StrEnum):
    """04 §6e lifecycle; dismissed is terminal from open."""
    open = "open"
    confirmed = "confirmed"
    assigned = "assigned"
    fix_pending_verification = "fix_pending_verification"
    closed = "closed"
    dismissed = "dismissed"


class Modality(StrEnum):
    """08 §5 future-modality note: text now; the rest schema-ready only."""
    text = "text"
    image = "image"
    social_post = "social_post"
    video = "video"


class RunMode(StrEnum):
    """08 §2: corpus = ground-truth snapshots by hash; live = crawl4ai."""
    corpus = "corpus"
    live = "live"


SSEEventType = Literal[
    "run_started", "node_started", "material_fetched", "property_status",
    "check_result", "node_finished", "needs_input", "run_awaiting_input",
    "run_resumed", "scores_updated", "run_finished", "error",
]


# --- contracts (07 §6) -------------------------------------------------------

class Property(BaseModel):
    id: str
    kind: PropertyKind
    url_or_handle: str
    config: dict[str, Any] = Field(default_factory=dict)


class Rule(BaseModel):
    id: str
    verbatim_text: str  # doc 05 §1, never paraphrased (guardrail)
    severity: Severity
    position: int


class BinaryCheck(BaseModel):
    id: str
    rule_id: str
    kind: CheckKind
    text: str
    evidence_criteria: str
    library_entry_id: str | None = None


class Material(BaseModel):
    id: str
    property_id: str
    ref: str
    kind: str
    modality: Modality = Modality.text
    media_ref: str | None = None
    content_hash: str
    extracted_text: str
    fetched_at: datetime


class CheckResult(BaseModel):
    material_id: str
    check_id: str
    trigger_met: bool
    requirement_met: bool | None = None
    axis_a: bool
    axis_b: bool | None = None  # None encodes "na" (07 §6 derivation rule)
    intersection_tag: IntersectionTag
    evidence_quote: str
    location: str
    reason: str
    confidence: float


class Flag(BaseModel):
    id: str
    run_id: str
    material_id: str | None = None
    check_id: str
    state: FlagState = FlagState.open
    assigned_team: str | None = None
    note: str | None = None
    modality: Modality = Modality.text
    media_ref: str | None = None
    cluster_id: str | None = None
    verdicts: CheckResult


class RunScores(BaseModel):
    draft: float | None = None
    verified: float | None = None
    per_property: dict[str, float] = Field(default_factory=dict)


class Disposition(BaseModel):
    action: Literal["confirm", "dismiss"]
    team: str | None = None
    note: str | None = None


class SSEEvent(BaseModel):
    """Envelope per 07 §6: persisted to events first, streamed second."""
    event_id: str
    run_id: str
    ts: datetime
    type: SSEEventType
    node: str | None = None
    property_id: str | None = None
    flag_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
