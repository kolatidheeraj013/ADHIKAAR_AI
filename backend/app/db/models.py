"""SQLAlchemy 2 domain models for the ADHIKAAR persistence layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Case(CreatedAtMixin, Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    language: Mapped[str] = mapped_column(String(2))
    channel: Mapped[str] = mapped_column(String(16))
    channel_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="COLLECTING")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    intent_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(CreatedAtMixin, Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_type_conf: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quality_conf: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_conf: Mapped[float | None] = mapped_column(Float, nullable=True)


class Fact(CreatedAtMixin, Base):
    __tablename__ = "facts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    key: Mapped[str] = mapped_column(String(128))
    value_json: Mapped[Any] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(16))
    source_doc_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    grounded: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    conf: Mapped[float | None] = mapped_column(Float, nullable=True)


class Decision(CreatedAtMixin, Base):
    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    scheme_id: Mapped[str] = mapped_column(String(128))
    outcome: Mapped[str] = mapped_column(String(24))
    rule_trace: Mapped[Any] = mapped_column(JSON)


class Application(CreatedAtMixin, Base):
    __tablename__ = "applications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    scheme_id: Mapped[str] = mapped_column(String(128))
    payload: Mapped[Any] = mapped_column(JSON)
    portal_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Escalation(CreatedAtMixin, Base):
    __tablename__ = "escalations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[Any] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    reviewer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(CreatedAtMixin, Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16))
    language: Mapped[str] = mapped_column(String(2))
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditEvent(CreatedAtMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[Any] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
