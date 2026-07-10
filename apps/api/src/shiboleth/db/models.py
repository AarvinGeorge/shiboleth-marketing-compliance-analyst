"""
meta:
  purpose: SQLAlchemy 2 ORM models — the full 01_spec §5 data model in
           Postgres (SQL + JSONB), including the 08 §5 future-modality
           columns (modality, media_ref) on materials and flags.
  contract: table-per-spec-line; string PKs (deterministic natural ids for
            seeded entities: R-01, D-01, turbotax-free). runs.mode added for
            the corpus|live contract (08 §2); events carries the full SSE
            envelope fields (07 §6: events are persisted rows first).
            Embedding vector column DEFERRED to the M3 migration (dimension
            depends on the embedding model chosen there). Schema changes are
            contract changes: surface to Aarvin first.
  deps: sqlalchemy 2 (JSONB via postgresql dialect).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, default="active")


class Property(Base):
    __tablename__ = "properties"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    kind: Mapped[str] = mapped_column(String)  # website | instagram | facebook
    url_or_handle: Mapped[str] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class Scorecard(Base):
    __tablename__ = "scorecards"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    scorecard_id: Mapped[str] = mapped_column(ForeignKey("scorecards.id"))
    verbatim_text: Mapped[str] = mapped_column(Text)  # doc 05 §1, never paraphrased
    severity: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String)  # disclosure | claim
    title: Mapped[str] = mapped_column(String)
    approved_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="approved")
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)


class BinaryCheck(Base):
    __tablename__ = "checks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"))
    kind: Mapped[str] = mapped_column(String)  # trigger | requirement
    text: Mapped[str] = mapped_column(Text)
    evidence_criteria: Mapped[str] = mapped_column(Text)
    library_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("library_entries.id"), nullable=True
    )


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    mode: Mapped[str] = mapped_column(String, default="live")  # corpus | live (08 §2)
    scorecard_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_config_json: Mapped[dict] = mapped_column("model_config", JSONB, default=dict)
    status: Mapped[str] = mapped_column(String, default="created")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)  # sparkline time series


class RunInventory(Base):
    __tablename__ = "run_inventory"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    ref: Mapped[str] = mapped_column(String)  # url or post ref
    content_hash: Mapped[str] = mapped_column(String)
    first_seen_run_id: Mapped[str | None] = mapped_column(String, nullable=True)


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id"))
    ref: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="page")
    modality: Mapped[str] = mapped_column(String, default="text")
    media_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, unique=True)
    extracted_text: Mapped[str] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # embedding vector: added by the M3 migration once the model/dim is chosen


class Cluster(Base):
    __tablename__ = "clusters"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    label: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="wording")


class Flag(Base):
    __tablename__ = "flags"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    material_id: Mapped[str | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True  # nullable: Missing findings
    )
    check_id: Mapped[str] = mapped_column(ForeignKey("checks.id"))
    axis_a: Mapped[bool] = mapped_column(Boolean)
    axis_b: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # NULL = na
    intersection_tag: Mapped[str] = mapped_column(String)
    evidence_quote: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    cluster_id: Mapped[str | None] = mapped_column(ForeignKey("clusters.id"), nullable=True)
    state: Mapped[str] = mapped_column(String, default="open")  # lifecycle (04 §6e)
    assigned_team: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispositioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modality: Mapped[str] = mapped_column(String, default="text")
    media_ref: Mapped[str | None] = mapped_column(String, nullable=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    flag_id: Mapped[str | None] = mapped_column(ForeignKey("flags.id"), nullable=True)
    property_id: Mapped[str | None] = mapped_column(String, nullable=True)
    node: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String)  # SSE envelope type (07 §6)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvalItem(Base):
    __tablename__ = "eval_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    harness: Mapped[str] = mapped_column(String)  # retrieval | decomposition | checker
    input: Mapped[dict] = mapped_column(JSONB, default=dict)
    expected: Mapped[dict] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(String, default="seed")  # seed | disposition
