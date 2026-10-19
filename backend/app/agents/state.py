"""Pydantic state and domain records for the Phase 3 walking skeleton."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["ta", "te", "hi", "en"]
Channel = Literal["web", "telegram"]
CaseStatus = Literal[
    "COLLECTING",
    "RECEIVED",
    "PROCESSING",
    "NEEDS_INFO",
    "NEEDS_DOCUMENTS",
    "NEEDS_REVIEW",
    "SUBMITTED",
    "COMPLETED",
    "NOT_ELIGIBLE",
    "FAILED_ESCALATED",
]


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    source_type: Literal["document", "declaration", "reviewer"]
    source_doc_id: str | None = None
    grounded: bool | None = None
    conf: float = Field(ge=0.0, le=1.0, default=1.0)


class DocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_id: str
    path: str
    doc_type: str
    doc_type_conf: float = Field(ge=0.0, le=1.0)
    quality: Literal["good", "blurry", "cropped", "too_dark"]
    quality_conf: float = Field(ge=0.0, le=1.0)
    ocr_text: str = ""
    ocr_conf: float = Field(ge=0.0, le=1.0, default=0.0)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    outcome: Literal["ELIGIBLE", "NOT_ELIGIBLE", "UNDETERMINED"]
    rule_trace: list[dict[str, Any]]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    text: str
    options: list[dict[str, Any]]


class Escalation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: Literal["OPEN", "RESOLVED"] = "OPEN"
    resolution: str | None = None


class ApplicationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    status: Literal["PENDING", "SUBMITTED", "FAILED"]
    portal_ref: str | None = None
    attempts: int = 0
    error: dict[str, Any] | None = None


class CitizenMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["info", "question", "result"]
    language: Language
    text: str
    options: list[dict[str, Any]] = Field(default_factory=list)


class CaseState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    language: Language
    channel: Channel
    channel_ref: str | None = None
    consent: bool = True
    voice_path: str | None = None
    transcript: str | None = None
    transcript_en: str | None = None
    document_paths: list[str] = Field(default_factory=list)
    documents: list[DocumentResult] = Field(default_factory=list)
    candidate_schemes: list[str] = Field(default_factory=list)
    facts: dict[str, Fact] = Field(default_factory=dict)
    missing_documents: dict[str, list[str]] = Field(default_factory=dict)
    decisions: dict[str, Decision] = Field(default_factory=dict)
    confidence: float | None = None
    pending_question: Question | None = None
    questions_asked: int = 0
    human_approved: bool = False
    status: CaseStatus = "RECEIVED"
    escalation: Escalation | None = None
    applications: dict[str, ApplicationResult] = Field(default_factory=dict)
    retries: dict[str, int] = Field(default_factory=dict)
    messages: list[CitizenMessage] = Field(default_factory=list)
    last_portal_error: dict[str, Any] | None = None
    reentry_from_documents: bool = False
    route: str = ""
