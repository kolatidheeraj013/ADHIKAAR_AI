"""ADHIKAAR Phase 8 HTTP API."""

from __future__ import annotations

import json
import wave
from collections.abc import Callable, Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import PlainTextResponse, StreamingResponse
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.graph import GraphDependencies, GraphRun, build_graph, resume_case, run_case
from app.agents.state import CaseState
from app.audit import log, mask_identifier, sanitize_evidence
from app.core.config import Settings, settings
from app.db.models import (
    Application,
    AuditEvent,
    Case,
    Decision,
    Document,
    Escalation,
    Fact,
    Message,
)
from app.db.session import build_engine, build_session_factory, init_db
from app.integrations.fakes import FakePortalClient, FakeRetriever, FakeSpeechClient
from app.integrations.interfaces import LLMClient
from app.integrations.llm import ProviderLLMClient
from app.integrations.notifier import NoopNotifier, TelegramNotifier
from app.integrations.storage import LocalStorageBackend
from app.rules.engine import load_schemes


class CreateCaseRequest(BaseModel):
    language: Literal["ta", "te", "hi", "en"] = "en"
    consent: bool
    channel: Literal["web", "telegram"] = "web"
    channel_ref: str | None = None


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class AnswerRequest(BaseModel):
    message_id: str | None = None
    option: Any


class ReviewerResumeRequest(BaseModel):
    action: Literal["approve", "reject", "request_docs"]
    edited_facts: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class _OfflineClassifier:
    def __init__(self, metadata: dict[str, dict[str, Any]]) -> None:
        self.metadata = metadata

    def classify(self, path: str) -> dict[str, Any]:
        return dict(
            self.metadata.get(
                path,
                {"doc_type": "other", "doc_type_conf": 0.8, "quality": "good", "quality_conf": 0.8},
            )
        )


class _OfflineOCR:
    def __init__(self, metadata: dict[str, dict[str, Any]]) -> None:
        self.metadata = metadata

    def ocr(self, path: str) -> dict[str, Any]:
        item = self.metadata.get(path, {})
        return {"text": item.get("ocr_text", "SAMPLE document"), "confidence": 0.95}


def _doc_type(filename: str) -> str:
    lowered = filename.lower()
    for needle, label in (
        ("land", "land_record"),
        ("patta", "land_record"),
        ("chitta", "land_record"),
        ("khasra", "land_record"),
        ("aadhaar", "aadhaar"),
        ("adhar", "aadhaar"),
        ("adhaar", "aadhaar"),
        ("passbook", "bank_passbook"),
        ("bank", "bank_passbook"),
        ("account", "bank_passbook"),
        ("income", "income_certificate"),
        ("aay", "income_certificate"),
        ("marksheet", "marksheet"),
        ("mark", "marksheet"),
        ("bonafide", "bonafide_certificate"),
    ):
        if needle in lowered:
            return label
    return "other"


def _offline_metadata(filename: str, path: str) -> dict[str, Any]:
    kind = _doc_type(filename)
    facts: dict[str, Any] = {}
    if kind == "land_record":
        facts = {"land_owned_hectares": 2.5, "holder_type": "individual"}
    elif kind == "aadhaar":
        facts = {"applicant_name": "Synthetic Applicant", "aadhaar_last4": "9012"}
    elif kind == "bank_passbook":
        facts = {"bank_account_number": "SYNTHETIC-ACCOUNT", "bank_ifsc": "SYNTHETICIFSC"}
    elif kind == "income_certificate":
        facts = {"family_income_annual": 120000.0}
    elif kind == "marksheet":
        facts = {"last_exam_percentage": 86.0}
    return {
        "doc_type": kind,
        "doc_type_conf": 0.98,
        "quality": "blurry" if "blurry" in filename.lower() else "good",
        "quality_conf": 0.95,
        "facts": facts,
        "ocr_text": "SAMPLE — NOT A REAL DOCUMENT "
        + " ".join(f"{k}={v}" for k, v in facts.items()),
        "path": path,
    }


class _OfflineLLM:
    def __init__(self, metadata: dict[str, dict[str, Any]]) -> None:
        self.metadata = metadata

    def extract_facts(
        self, text: str, source_type: str, source_doc_id: str | None, target_keys: list[str]
    ) -> dict[str, Any]:
        if source_type == "declaration":
            lowered = text.lower()
            if "tax" in lowered:
                return {"is_income_tax_payer": "nobody" not in lowered and "no tax" not in lowered}
            if "recognized" in lowered:
                return {"institution_recognized": "not" not in lowered}
            return {}
        facts = self.metadata.get(source_doc_id or "", {}).get("facts", {})
        return {key: facts[key] for key in target_keys if key in facts}

    def extract_field(self, text: str, field: str, source_doc_id: str | None) -> Any:
        return self.metadata.get(source_doc_id or "", {}).get("facts", {}).get(field)

    def explain(self, outcome: str, trace: list[dict[str, Any]], language: str) -> str:
        return {
            "ELIGIBLE": "Your MOCK scheme application is eligible.",
            "NOT_ELIGIBLE": (
                "Your MOCK scheme application is not eligible under the recorded rules."
            ),
        }.get(outcome, "More information is required for this MOCK scheme application.")


class _ServiceState:
    def __init__(self, configured: Settings) -> None:
        self.settings = configured
        if (
            configured.database_url.startswith("sqlite:///")
            and ":memory:" not in configured.database_url
        ):
            database_path = Path(configured.database_url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = build_engine(configured.database_url)
        init_db(self.engine)
        self.sessions = build_session_factory(self.engine)
        self.storage = LocalStorageBackend(configured.storage_dir)
        self.runs: dict[str, GraphRun] = {}
        self.thread_ids: dict[str, str] = {}
        self.upload_metadata: dict[str, dict[str, Any]] = {}
        self.voice_paths: dict[str, str] = {}
        self.message_keys: dict[str, set[str]] = {}
        self.run_counts: dict[str, int] = {}
        self.notifier = NoopNotifier()
        self.notifiers: dict[str, NoopNotifier | TelegramNotifier] = {}
        self.pending_notification_results: dict[str, tuple[str, str, bool, int, str | None]] = {}
        self.checkpointer = InMemorySaver()
        self.runtime_factory: Callable[[Session, str], GraphDependencies] = self._runtime

    def _llm_for_runtime(self, metadata: dict[str, dict[str, Any]]) -> LLMClient:
        """Select the configured provider, otherwise preserve offline behavior."""
        if self.settings.llm_base_url:
            return ProviderLLMClient(
                provider=self.settings.llm_provider,
                api_key=self.settings.llm_api_key,
                model=self.settings.llm_model,
                base_url=self.settings.llm_base_url,
                # An explicitly configured endpoint is an intentional opt-in,
                # including local endpoints that do not use an API key.
                demo_mode="live",
            )
        return _OfflineLLM(metadata)

    def _notification_result(
        self,
        message_id: str,
        case_id: str,
        kind: str,
        delivered: bool,
        attempts: int,
        error: str | None,
    ) -> None:
        """Apply delivery state from a background notifier worker.

        A graph run may not have committed its message row yet when the
        notifier completes. Keep that result briefly in memory; the run
        persistence path applies it after inserting the row.
        """
        session = self.sessions()
        try:
            message = session.get(Message, UUID(message_id))
            if message is None:
                self.pending_notification_results[message_id] = (
                    case_id,
                    kind,
                    delivered,
                    attempts,
                    error,
                )
                return
            message.delivered = delivered
            if not delivered:
                log(
                    session,
                    case_id=UUID(case_id),
                    actor="notifier",
                    event_type="notification.delivery_failed",
                    summary="Citizen notification could not be delivered",
                    evidence={
                        "message_id": message_id,
                        "kind": kind,
                        "attempts": attempts,
                        "error_type": error or "unknown",
                    },
                )
            session.commit()
        finally:
            session.close()

    def _notifier_for_case(self, case: Case) -> NoopNotifier | TelegramNotifier:
        case_key = str(case.id)
        existing = self.notifiers.get(case_key)
        if existing is not None:
            return existing
        if case.channel == "telegram" and case.channel_ref:
            notifier: NoopNotifier | TelegramNotifier = TelegramNotifier(
                bot_internal_url=self.settings.bot_internal_url,
                service_token=self.settings.service_token,
                chat_id=case.channel_ref,
                timeout_seconds=self.settings.notifier_timeout_seconds,
                on_delivery=self._notification_result,
            )
        else:
            notifier = self.notifier
        self.notifiers[case_key] = notifier
        return notifier

    def _runtime(self, session: Session, case_id: str) -> GraphDependencies:
        metadata = {
            path: value
            for path, value in self.upload_metadata.items()
            if path.startswith(f"{case_id}/")
        }
        documents = session.scalars(select(Document).where(Document.case_id == UUID(case_id))).all()
        case = session.get(Case, UUID(case_id))
        if case is None:
            raise ValueError("case not found while building graph runtime")
        for document in documents:
            if not document.storage_path or document.storage_path in metadata:
                continue
            recovered = _offline_metadata(
                f"{document.doc_type or 'document'}.png", document.storage_path
            )
            recovered["quality"] = document.quality or recovered["quality"]
            recovered["quality_conf"] = document.quality_conf or recovered["quality_conf"]
            metadata[document.storage_path] = recovered
        existing_types = {
            metadata[d.storage_path]["doc_type"]
            for d in documents
            if d.storage_path
            and d.storage_path in metadata
            and metadata[d.storage_path].get("doc_type") != "other"
        }
        candidate_reqs = ["aadhaar", "land_record", "bank_passbook"]
        if case.intent_text and any(
            w in case.intent_text.lower()
            for w in ("scholar", "study", "education", "school", "college")
        ):
            candidate_reqs = ["aadhaar", "income_certificate", "marksheet", "bonafide_certificate"]
        needed = [req for req in candidate_reqs if req not in existing_types]
        for document in documents:
            if not document.storage_path:
                continue
            m = metadata.get(document.storage_path)
            if m and (m.get("doc_type") == "other" or not m.get("doc_type")) and needed:
                assigned_type = needed.pop(0)
                assigned_meta = _offline_metadata(f"{assigned_type}.png", document.storage_path)
                m.update(assigned_meta)
                document.doc_type = assigned_type
                document.doc_type_conf = 0.95
        return GraphDependencies(
            session=session,
            speech=FakeSpeechClient(
                "I need help with PM-Kisan; nobody in my family pays income tax"
            ),
            classifier=_OfflineClassifier(metadata),
            ocr=_OfflineOCR(metadata),
            llm=self._llm_for_runtime(metadata),
            retriever=FakeRetriever(),
            portal=FakePortalClient(),
            notifier=self._notifier_for_case(case),
            storage=self.storage,
            auto_submit_threshold=self.settings.auto_submit_threshold,
            review_threshold=self.settings.review_threshold,
        )


app = FastAPI(title="ADHIKAAR Backend", version="0.8.0")
app.state.services = _ServiceState(settings)


def _services() -> _ServiceState:
    return app.state.services


def _session() -> Generator[Session, None, None]:
    session = _services().sessions()
    try:
        yield session
    finally:
        session.close()


def _case_or_404(case_id: UUID, session: Session) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


def _require_service(token: str | None) -> None:
    if token != _services().settings.service_token:
        raise HTTPException(status_code=401, detail="service authentication required")


def _require_reviewer(token: str | None) -> None:
    if token != _services().settings.reviewer_password:
        raise HTTPException(status_code=401, detail="reviewer authentication required")


def _safe_text(value: str) -> str:
    return str(sanitize_evidence(value))


def _mask_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered.endswith("last4"):
        digits = "".join(character for character in str(value) if character.isdigit())
        return f"***{digits[-4:]}" if digits else "[REDACTED]"
    if any(marker in lowered for marker in ("aadhaar", "account", "ifsc", "phone", "email")):
        return mask_identifier(str(value))
    if lowered in {"applicant_name", "name"}:
        return "[REDACTED]"
    return value


def _safe_case(case: Case, session: Session) -> dict[str, Any]:
    messages = session.scalars(
        select(Message).where(Message.case_id == case.id).order_by(Message.created_at)
    ).all()
    decision = session.scalar(
        select(Decision).where(Decision.case_id == case.id).order_by(Decision.created_at.desc())
    )
    return {
        "case_id": str(case.id),
        "status": case.status,
        "language": case.language,
        "channel": case.channel,
        "channel_ref": case.channel_ref,
        "decision_summary": (
            {"scheme_id": decision.scheme_id, "outcome": decision.outcome} if decision else None
        ),
        "documents": [
            {
                "id": str(item.id),
                "doc_type": item.doc_type,
                "quality": item.quality,
            }
            for item in session.scalars(select(Document).where(Document.case_id == case.id)).all()
        ],
        "messages": [
            {
                "id": str(item.id),
                "kind": item.kind,
                "text": _safe_text(item.text),
                "options": (item.payload or {}).get("options", [])
                if item.kind == "question"
                else [],
                "created_at": item.created_at.isoformat(),
            }
            for item in messages
        ],
    }


def _persist_run(case_id: UUID, result: GraphRun, session: Session) -> None:
    case = _case_or_404(case_id, session)
    state = result.state
    case.status = state.status
    case.updated_at = datetime.now(timezone.utc)
    session.execute(delete(Fact).where(Fact.case_id == case_id))
    documents_by_path = {
        item.storage_path: item.id
        for item in session.scalars(select(Document).where(Document.case_id == case_id)).all()
        if item.storage_path
    }
    documents = {
        item.storage_path: item
        for item in session.scalars(select(Document).where(Document.case_id == case_id)).all()
        if item.storage_path
    }
    for document in state.documents:
        row = documents.get(document.path)
        if row is None:
            continue
        row.doc_type = document.doc_type
        row.doc_type_conf = document.doc_type_conf
        row.quality = document.quality
        row.quality_conf = document.quality_conf
        row.ocr_text = document.ocr_text or None
        row.ocr_conf = document.ocr_conf
    for fact in state.facts.values():
        session.add(
            Fact(
                case_id=case_id,
                key=fact.key,
                value_json=fact.value,
                source_type=fact.source_type,
                source_doc_id=documents_by_path.get(fact.source_doc_id),
                grounded=fact.grounded,
                conf=fact.conf,
            )
        )
    session.execute(delete(Decision).where(Decision.case_id == case_id))
    for decision in state.decisions.values():
        session.add(
            Decision(
                case_id=case_id,
                scheme_id=decision.scheme_id,
                outcome=decision.outcome,
                rule_trace=decision.rule_trace,
            )
        )
    session.execute(delete(Application).where(Application.case_id == case_id))
    for application in state.applications.values():
        session.add(
            Application(
                case_id=case_id,
                scheme_id=application.scheme_id,
                payload={},
                portal_ref=application.portal_ref,
                status=application.status,
                attempts=application.attempts,
            )
        )
    if state.escalation:
        escalation_row = session.scalar(
            select(Escalation).where(Escalation.case_id == case_id, Escalation.status == "OPEN")
        )
        if escalation_row is None:
            session.add(
                Escalation(
                    case_id=case_id,
                    reason=state.escalation.reason,
                    evidence=sanitize_evidence(state.escalation.evidence),
                    status=state.escalation.status,
                    resolution=state.escalation.resolution,
                )
            )
        elif state.escalation.status == "RESOLVED":
            escalation_row.status = "RESOLVED"
            escalation_row.resolution = state.escalation.resolution
            escalation_row.reviewer_id = "reviewer"
            escalation_row.resolved_at = datetime.now(timezone.utc)
    keys = _services().message_keys.setdefault(str(case_id), set())
    session.flush()
    existing_messages = {
        (item.kind, item.text)
        for item in session.scalars(select(Message).where(Message.case_id == case_id)).all()
    }
    if (
        state.pending_question
        and ("question", state.pending_question.text) not in existing_messages
    ):
        session.add(
            Message(
                case_id=case_id,
                direction="out",
                kind="question",
                language=state.language,
                text=_safe_text(state.pending_question.text),
                payload={"options": state.pending_question.options},
                delivered=True,
            )
        )
        existing_messages.add(("question", _safe_text(state.pending_question.text)))
    for message in state.messages:
        key = f"{message.kind}:{message.text}:{json.dumps(message.options, sort_keys=True)}"
        if key in keys or (message.kind, _safe_text(message.text)) in existing_messages:
            keys.add(key)
            continue
        keys.add(key)
        existing_messages.add((message.kind, _safe_text(message.text)))
        session.add(
            Message(
                case_id=case_id,
                direction="out",
                kind=message.kind,
                language=message.language,
                text=_safe_text(message.text),
                payload={"options": message.options},
                delivered=True,
            )
        )
    session.commit()
    # A notifier worker can finish before this graph transaction commits. Apply
    # any result that was buffered while the message row was not yet visible.
    if self_pending := [
        (message_id, result)
        for message_id, result in _services().pending_notification_results.items()
        if result[0] == str(case_id)
    ]:
        result_session = _services().sessions()
        try:
            for message_id, result in self_pending:
                message = result_session.get(Message, UUID(message_id))
                if message is None:
                    continue
                _, kind, delivered, attempts, error = result
                message.delivered = delivered
                if not delivered:
                    log(
                        result_session,
                        case_id=case_id,
                        actor="notifier",
                        event_type="notification.delivery_failed",
                        summary="Citizen notification could not be delivered",
                        evidence={
                            "message_id": message_id,
                            "kind": kind,
                            "attempts": attempts,
                            "error_type": error or "unknown",
                        },
                    )
                _services().pending_notification_results.pop(message_id, None)
            result_session.commit()
        finally:
            result_session.close()


def _state_for_case(case: Case, session: Session) -> CaseState:
    existing = _services().runs.get(str(case.id))
    documents = session.scalars(select(Document).where(Document.case_id == case.id)).all()
    doc_paths = [item.storage_path for item in documents if item.storage_path]
    if existing:
        st = existing.state.model_copy(deep=True)
        # Ensure any newly uploaded documents are merged into the state
        st.document_paths = list(dict.fromkeys(st.document_paths + doc_paths))
        return st
    return CaseState(
        case_id=str(case.id),
        language=case.language,
        channel=case.channel,
        channel_ref=case.channel_ref,
        consent=case.consent_at is not None,
        voice_path=case.voice_storage_path,
        transcript=case.intent_text,
        document_paths=doc_paths,
        status="RECEIVED",
    )


def _run_case(case_id: str, *, state: CaseState | None = None) -> None:
    service = _services()
    session = service.sessions()
    try:
        case = session.get(Case, UUID(case_id))
        if case is None:
            return
        current = state or _state_for_case(case, session)
        runtime = service.runtime_factory(session, case_id)
        graph = build_graph(runtime, checkpointer=service.checkpointer)
        service.run_counts[case_id] = service.run_counts.get(case_id, 0) + 1
        thread_id = service.thread_ids.get(case_id) or case_id
        if service.run_counts[case_id] > 1 and current.status == "NEEDS_DOCUMENTS":
            thread_id = f"{case_id}:{service.run_counts[case_id]}"
        service.thread_ids[case_id] = thread_id
        result = run_case(graph, current, thread_id=thread_id)
        service.runs[case_id] = result
        _persist_run(UUID(case_id), result, session)
    except Exception as exc:
        case = session.get(Case, UUID(case_id))
        if case:
            case.status = "FAILED_ESCALATED"
            log(
                session,
                case_id=UUID(case_id),
                actor="api",
                event_type="case.error",
                summary="Processing could not be completed",
                evidence={"error_type": type(exc).__name__},
            )
            session.commit()
    finally:
        session.close()


def _validate_size(content: bytes, label: str) -> None:
    if len(content) > _services().settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"{label} exceeds the upload limit")


def _image_kind(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _audio_kind(content: bytes) -> str | None:
    if content.startswith(b"OggS"):
        return "audio/ogg"
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "audio/wav"
    if content.startswith(b"ID3") or content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    return None


def _audio_duration_seconds(content: bytes, kind: str) -> float | None:
    """Return a duration when it is cheaply verifiable from the uploaded bytes."""
    if kind != "audio/wav":
        return None
    try:
        import io

        with wave.open(io.BytesIO(content)) as wav:
            frame_rate = wav.getframerate()
            return wav.getnframes() / frame_rate if frame_rate else None
    except (wave.Error, EOFError, ValueError):
        return None


@app.get("/health")
async def health(session: Session = Depends(_session)) -> dict[str, str]:
    db_status = "healthy"
    try:
        session.execute(select(1))
    except Exception:
        db_status = "unhealthy"

    checkpointer_status = "ready" if _services().checkpointer is not None else "not_ready"
    is_healthy = db_status == "healthy" and checkpointer_status == "ready"
    overall_status = "ok" if is_healthy else "degraded"
    return {
        "service": "backend",
        "status": overall_status,
        "db": db_status,
        "checkpointer": checkpointer_status,
    }


@app.get("/stats")
@app.get("/metrics")
async def system_stats(
    format: str | None = None,
    session: Session = Depends(_session),
) -> Any:
    cases = session.scalars(select(Case)).all()
    total_cases = len(cases)
    by_status: dict[str, int] = {}
    resolution_times: list[float] = []

    terminal_statuses = {"COMPLETED", "SUBMITTED", "NOT_ELIGIBLE", "FAILED_ESCALATED"}
    for c in cases:
        by_status[c.status] = by_status.get(c.status, 0) + 1
        if c.status in terminal_statuses and c.created_at and c.updated_at:
            delta = (c.updated_at - c.created_at).total_seconds()
            resolution_times.append(max(0.0, delta))

    escalations = session.scalars(select(Escalation)).all()
    open_escalations = sum(1 for e in escalations if e.status == "OPEN")
    total_escalations = len(escalations)

    auto_submits = by_status.get("SUBMITTED", 0) + by_status.get("COMPLETED", 0)
    auto_submit_rate = (
        round((auto_submits / total_cases) * 100.0, 1) if total_cases > 0 else 0.0
    )
    escalation_rate = (
        round((total_escalations / total_cases) * 100.0, 1) if total_cases > 0 else 0.0
    )
    avg_resolution_seconds = (
        round(sum(resolution_times) / len(resolution_times), 2)
        if resolution_times
        else 0.0
    )

    events = session.scalars(select(AuditEvent)).all()
    latencies = [
        e.evidence.get("duration_ms")
        for e in events
        if e.evidence
        and isinstance(e.evidence.get("duration_ms"), (int, float))
        and e.evidence.get("duration_ms") > 0
    ]
    avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    payload = {
        "total_cases": total_cases,
        "by_status": by_status,
        "auto_submitted_count": auto_submits,
        "submitted_count": auto_submits,
        "escalated_count": open_escalations,
        "total_escalations": total_escalations,
        "auto_submit_rate_pct": auto_submit_rate,
        "escalation_rate_pct": escalation_rate,
        "average_resolution_time_seconds": avg_resolution_seconds,
        "avg_resolution_time_seconds": avg_resolution_seconds,
        "total_audit_events": len(events),
        "avg_node_latency_ms": avg_latency_ms,
    }

    if format == "prometheus":
        lines = [
            "# HELP adhikaar_total_cases Total number of citizen cases processed",
            "# TYPE adhikaar_total_cases counter",
            f"adhikaar_total_cases {total_cases}",
            "# HELP adhikaar_auto_submitted Total number of auto-submitted cases",
            "# TYPE adhikaar_auto_submitted counter",
            f"adhikaar_auto_submitted {auto_submits}",
            "# HELP adhikaar_escalated Total number of escalated cases",
            "# TYPE adhikaar_escalated counter",
            f"adhikaar_escalated {total_escalations}",
            "# HELP adhikaar_avg_resolution_seconds Average time to resolution in seconds",
            "# TYPE adhikaar_avg_resolution_seconds gauge",
            f"adhikaar_avg_resolution_seconds {avg_resolution_seconds}",
            "# HELP adhikaar_avg_node_latency_ms Average execution latency per node in ms",
            "# TYPE adhikaar_avg_node_latency_ms gauge",
            f"adhikaar_avg_node_latency_ms {avg_latency_ms}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n")

    return payload


@app.post("/cases")
async def create_case(
    payload: CreateCaseRequest, session: Session = Depends(_session)
) -> dict[str, str]:
    if not payload.consent:
        raise HTTPException(status_code=422, detail="consent is required before creating a case")
    case = Case(
        language=payload.language,
        channel=payload.channel,
        channel_ref=payload.channel_ref,
        status="COLLECTING",
        consent_at=datetime.now(timezone.utc),
    )
    session.add(case)
    session.flush()
    log(
        session,
        case_id=case.id,
        actor="citizen",
        event_type="case.created",
        summary="Case created with consent",
        evidence={"channel": payload.channel, "language": payload.language},
    )
    session.commit()
    return {"case_id": str(case.id)}


@app.get("/cases/active")
async def active_case(
    channel: str, channel_ref: str, x_service_token: str | None = Header(default=None)
) -> dict[str, Any]:
    _require_service(x_service_token)
    session = _services().sessions()
    try:
        case = session.scalar(
            select(Case)
            .where(
                Case.channel == channel,
                Case.channel_ref == channel_ref,
                Case.status.not_in(["COMPLETED", "NOT_ELIGIBLE", "FAILED_ESCALATED"]),
            )
            .order_by(Case.created_at.desc())
        )
        if case and case.created_at:
            created = case.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - created).total_seconds() > 3600:
                case = None
        return {"case": _safe_case(case, session) if case else None}
    finally:
        session.close()


@app.get("/cases/latest")
async def latest_case(
    channel: str, channel_ref: str, x_service_token: str | None = Header(default=None)
) -> dict[str, Any]:
    """Return the latest case for status/recovery, including terminal results."""
    _require_service(x_service_token)
    session = _services().sessions()
    try:
        case = session.scalar(
            select(Case)
            .where(Case.channel == channel, Case.channel_ref == channel_ref)
            .order_by(Case.created_at.desc())
        )
        return {"case": _safe_case(case, session) if case else None}
    finally:
        session.close()


@app.post("/cases/{case_id}/text")
async def add_text(
    case_id: UUID, payload: TextRequest, session: Session = Depends(_session)
) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    if case.consent_at is None:
        raise HTTPException(status_code=422, detail="consent is required before upload")
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text must not be blank")
    case.intent_text = text
    case.updated_at = datetime.now(timezone.utc)
    log(
        session,
        case_id=case_id,
        actor="citizen",
        event_type="input.text",
        summary="Typed request received",
        evidence={"length": len(case.intent_text)},
    )
    session.commit()
    return {"case_id": str(case_id), "received": True}


@app.post("/cases/{case_id}/voice")
async def add_voice(
    case_id: UUID, file: UploadFile = File(...), session: Session = Depends(_session)
) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    if case.consent_at is None:
        raise HTTPException(status_code=422, detail="consent is required before upload")
    content = await file.read(_services().settings.max_upload_mb * 1024 * 1024 + 1)
    _validate_size(content, "voice file")
    kind = _audio_kind(content)
    if not kind or (
        file.content_type and file.content_type not in {kind, "application/octet-stream"}
    ):
        raise HTTPException(status_code=415, detail="voice must be OGG, WAV, or MP3 audio")
    duration = _audio_duration_seconds(content, kind)
    if duration is not None and duration > _services().settings.max_voice_seconds:
        raise HTTPException(status_code=422, detail="voice exceeds the duration limit")
    path = _services().storage.store(str(case_id), file.filename or "voice.ogg", content)
    _services().upload_metadata[path] = {"filename": file.filename or "voice.ogg"}
    _services().voice_paths[str(case_id)] = path
    case.voice_storage_path = path
    active = _services().runs.get(str(case_id))
    if active:
        active.state.voice_path = path
    log(
        session,
        case_id=case_id,
        actor="citizen",
        event_type="input.voice",
        summary="Voice request received",
        evidence={"media_type": kind, "size": len(content)},
    )
    session.commit()
    return {"case_id": str(case_id), "received": True}


@app.post("/cases/{case_id}/documents")
async def add_document(
    case_id: UUID,
    file: UploadFile = File(...),
    doc_type: str | None = Query(default=None),
    session: Session = Depends(_session),
) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    if case.consent_at is None:
        raise HTTPException(status_code=422, detail="consent is required before upload")
    existing_count = len(session.scalars(select(Document).where(Document.case_id == case_id)).all())
    if existing_count >= _services().settings.max_docs_per_case:
        raise HTTPException(status_code=422, detail="maximum documents reached for this case")
    content = await file.read(_services().settings.max_upload_mb * 1024 * 1024 + 1)
    _validate_size(content, "document")
    kind = _image_kind(content)
    if not kind or (
        file.content_type and file.content_type not in {kind, "application/octet-stream"}
    ):
        raise HTTPException(status_code=415, detail="only JPEG, PNG, and WebP images are accepted")
    name = file.filename or "document.png"
    if doc_type and doc_type.strip().lower() in {
        "aadhaar",
        "land_record",
        "bank_passbook",
        "income_certificate",
        "marksheet",
        "bonafide_certificate",
    }:
        name = f"{doc_type.strip().lower()}.png"
    path = _services().storage.store(str(case_id), name, content)
    metadata = _offline_metadata(name, path)
    _services().upload_metadata[path] = metadata
    active = _services().runs.get(str(case_id))
    if active and path not in active.state.document_paths:
        active.state.document_paths.append(path)
    document = Document(
        case_id=case_id,
        storage_path=path,
        doc_type=metadata["doc_type"],
        doc_type_conf=metadata["doc_type_conf"],
        quality=metadata["quality"],
        quality_conf=metadata["quality_conf"],
    )
    session.add(document)
    session.flush()
    log(
        session,
        case_id=case_id,
        actor="citizen",
        event_type="input.document",
        summary="Document received",
        evidence={
            "document_id": str(document.id),
            "media_type": kind,
            "size": len(content),
            "doc_type": metadata["doc_type"],
        },
    )
    session.commit()
    return {
        "case_id": str(case_id),
        "document_id": str(document.id),
        "doc_type": metadata["doc_type"],
        "received": True,
    }


@app.post("/cases/{case_id}/documents/{document_id}/classify")
async def classify_document(
    case_id: UUID,
    document_id: UUID,
    doc_type: str = Query(...),
    session: Session = Depends(_session),
) -> dict[str, Any]:
    _case_or_404(case_id, session)
    document = session.scalar(
        select(Document).where(Document.case_id == case_id, Document.id == document_id)
    )
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    clean = doc_type.strip().lower()
    valid = {
        "aadhaar",
        "land_record",
        "bank_passbook",
        "income_certificate",
        "marksheet",
        "bonafide_certificate",
        "other",
    }
    if clean in valid:
        document.doc_type = clean
        document.doc_type_conf = 0.99
        if document.storage_path:
            meta = _offline_metadata(f"{clean}.png", document.storage_path)
            _services().upload_metadata[document.storage_path] = meta
        session.commit()
    return {"case_id": str(case_id), "document_id": str(document_id), "doc_type": document.doc_type}


@app.post("/cases/{case_id}/start")
async def start_case(
    case_id: UUID, background_tasks: BackgroundTasks, session: Session = Depends(_session)
) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    docs = session.scalars(
        select(Document).where(Document.case_id == case_id, Document.storage_path.is_not(None))
    ).all()
    if case.consent_at is None:
        raise HTTPException(status_code=422, detail="consent is required")
    existing = _services().runs.get(str(case_id))
    if not case.intent_text and not (existing and existing.state.voice_path):
        case.intent_text = "Citizen request for welfare scheme entitlement check"
        session.commit()
    if not docs:
        raise HTTPException(status_code=422, detail="upload at least one document first")
    has_new_docs = bool(
        existing
        and any(
            d.storage_path and d.storage_path not in existing.state.document_paths
            for d in docs
        )
    )
    if existing and not has_new_docs and case.status in {
        "PROCESSING",
        "NEEDS_INFO",
        "NEEDS_REVIEW",
        "SUBMITTED",
        "COMPLETED",
        "NOT_ELIGIBLE",
        "FAILED_ESCALATED",
    }:
        return {"case_id": str(case_id), "status": case.status, "idempotent": True}
    if not existing and case.status in {
        "SUBMITTED",
        "COMPLETED",
        "NOT_ELIGIBLE",
        "FAILED_ESCALATED",
    }:
        return {"case_id": str(case_id), "status": case.status, "idempotent": True}
    case.status = "PROCESSING"
    session.commit()
    current = _state_for_case(case, session)
    current.transcript = case.intent_text or current.transcript
    current.voice_path = (
        existing.state.voice_path
        if existing and existing.state.voice_path
        else case.voice_storage_path or _services().voice_paths.get(str(case_id))
    )
    background_tasks.add_task(_run_case, str(case_id), state=current)
    return {"case_id": str(case_id), "status": "PROCESSING", "idempotent": False}


@app.post("/cases/{case_id}/answers")
async def answer_case(
    case_id: UUID, payload: AnswerRequest, session: Session = Depends(_session)
) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    if case.status != "NEEDS_INFO":
        raise HTTPException(status_code=409, detail="case has no pending question")
    if str(case_id) not in _services().runs:
        raise HTTPException(status_code=409, detail="case run is not resumable")
    pending = _services().runs[str(case_id)].state.pending_question
    if pending is None:
        raise HTTPException(status_code=409, detail="case has no pending question")
    if payload.message_id:
        question_message = session.scalar(
            select(Message)
            .where(
                Message.case_id == case_id,
                Message.kind == "question",
            )
            .order_by(Message.created_at.desc())
        )
        if question_message is None or str(question_message.id).replace("-", "") != str(
            payload.message_id
        ).replace("-", ""):
            raise HTTPException(status_code=409, detail="question is no longer current")
    option = payload.option
    if isinstance(option, str):
        normalized = option.strip().lower()
        if normalized in {"yes", "true", "1"}:
            option = True
        elif normalized in {"no", "false", "0"}:
            option = False
    if not isinstance(option, bool):
        raise HTTPException(status_code=422, detail="answer option must be yes or no")
    session.close()
    runtime_session = _services().sessions()
    try:
        result = resume_case(
            build_graph(
                _services().runtime_factory(runtime_session, str(case_id)),
                checkpointer=_services().checkpointer,
            ),
            str(case_id),
            {"value": option},
        )
        _services().runs[str(case_id)] = result
        _persist_run(case_id, result, runtime_session)
    finally:
        runtime_session.close()
    return {"case_id": str(case_id), "status": _services().runs[str(case_id)].state.status}


@app.get("/cases/{case_id}")
async def get_case(case_id: UUID, session: Session = Depends(_session)) -> dict[str, Any]:
    return _safe_case(_case_or_404(case_id, session), session)


@app.get("/cases/{case_id}/events")
async def case_events(case_id: UUID, session: Session = Depends(_session)) -> StreamingResponse:
    case = _case_or_404(case_id, session)
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.ts)
    ).all()
    safe_events = [
        {
            "event_type": item.event_type,
            "summary": _safe_text(item.summary),
            "status": case.status,
            "ts": item.ts.isoformat(),
        }
        for item in events
    ]

    async def stream() -> Any:
        for event in safe_events:
            yield f"data: {json.dumps(event)}\n\n"
        yield f"event: status\ndata: {json.dumps({'status': case.status})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/cases/{case_id}/track")
@app.get("/cases/{case_id}/track")
async def track_case(case_id: UUID, session: Session = Depends(_session)) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    app_record = session.scalar(
        select(Application).where(Application.case_id == case_id)
    )
    if app_record is None or not app_record.portal_ref:
        return {
            "case_id": str(case_id),
            "status": case.status,
            "message": "No submitted portal application found for this case",
        }

    portal_ref = app_record.portal_ref
    scheme_id = app_record.scheme_id

    portal = _services().runtime_factory(session, str(case_id)).portal
    verification = portal.verify(portal_ref)

    portal_status = verification.get("status", "unknown")
    sla_escalated = False

    if portal_status == "stalled":
        sla_escalated = True
        escalation = session.scalar(
            select(Escalation).where(Escalation.case_id == case_id)
        )
        if escalation is None:
            escalation = Escalation(
                case_id=case_id,
                reason="portal_sla_stalled",
                evidence={"portal_ref": portal_ref, "days_stalled": 45, "action": "nudge_portal"},
                status="OPEN",
            )
            session.add(escalation)
        else:
            escalation.status = "OPEN"
            escalation.reason = "portal_sla_stalled"

        case.status = "NEEDS_REVIEW"

        log(
            session,
            case_id=str(case_id),
            actor="agent",
            event_type="tracking.sla_stalled",
            summary=f"Portal application {portal_ref} stalled past SLA; escalated to reviewer",
            evidence={"portal_ref": portal_ref, "days_stalled": 45, "status": "stalled"},
        )
        session.commit()
    else:
        log(
            session,
            case_id=str(case_id),
            actor="agent",
            event_type="tracking.status_checked",
            summary=f"Polled portal status for {portal_ref}: {portal_status}",
            evidence={"portal_ref": portal_ref, "status": portal_status},
        )
        session.commit()

    return {
        "case_id": str(case_id),
        "portal_ref": portal_ref,
        "scheme_id": scheme_id,
        "portal_status": portal_status,
        "sla_escalated": sla_escalated,
    }


@app.delete("/cases/{case_id}")
async def delete_case(case_id: UUID, session: Session = Depends(_session)) -> dict[str, Any]:
    case = _case_or_404(case_id, session)
    documents = session.scalars(select(Document).where(Document.case_id == case_id)).all()
    paths_to_delete = {document.storage_path for document in documents if document.storage_path}
    for document in documents:
        if document.storage_path:
            document.storage_path = None
        document.ocr_text = None
    voice_path = _services().voice_paths.pop(str(case_id), None)
    voice_path = voice_path or case.voice_storage_path
    if voice_path:
        paths_to_delete.add(voice_path)
    case.voice_storage_path = None
    metadata_paths = [
        path for path in _services().upload_metadata if path.startswith(f"{case_id}/")
    ]
    paths_to_delete.update(metadata_paths)
    for path in paths_to_delete:
        _services().storage.delete(path)
        _services().upload_metadata.pop(path, None)
    session.execute(delete(Fact).where(Fact.case_id == case_id))
    case.intent_text = None
    log(
        session,
        case_id=case_id,
        actor="citizen",
        event_type="case.deleted",
        summary="Citizen data deleted; redacted audit retained",
        evidence={"document_ids": [str(item.id) for item in documents]},
    )
    session.commit()
    _services().runs.pop(str(case_id), None)
    _services().thread_ids.pop(str(case_id), None)
    _services().run_counts.pop(str(case_id), None)
    _services().message_keys.pop(str(case_id), None)
    return {"case_id": str(case_id), "deleted": True}


@app.get("/schemes")
async def schemes() -> list[dict[str, Any]]:
    return [
        {
            "scheme_id": item.scheme_id,
            "name": item.name,
            "benefit": item.benefit,
            "required_documents": item.required_documents,
        }
        for item in load_schemes().values()
    ]


@app.get("/reviewer/queue")
async def reviewer_queue(
    x_reviewer_token: str | None = Header(default=None), session: Session = Depends(_session)
) -> list[dict[str, Any]]:
    _require_reviewer(x_reviewer_token)
    rows = session.scalars(
        select(Escalation).where(Escalation.status == "OPEN").order_by(Escalation.created_at)
    ).all()
    return [
        {
            "case_id": str(row.case_id),
            "reason": _safe_text(row.reason),
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/reviewer/{case_id}")
async def reviewer_case(
    case_id: UUID,
    x_reviewer_token: str | None = Header(default=None),
    session: Session = Depends(_session),
) -> dict[str, Any]:
    _require_reviewer(x_reviewer_token)
    case = _case_or_404(case_id, session)
    docs = session.scalars(select(Document).where(Document.case_id == case_id)).all()
    facts = session.scalars(select(Fact).where(Fact.case_id == case_id)).all()
    decisions = session.scalars(select(Decision).where(Decision.case_id == case_id)).all()
    escalation = session.scalar(
        select(Escalation)
        .where(Escalation.case_id == case_id)
        .order_by(Escalation.created_at.desc())
    )
    return {
        "case_id": str(case_id),
        "status": case.status,
        "documents": [
            {
                "id": str(item.id),
                "doc_type": item.doc_type,
                "quality": item.quality,
                "ocr_confidence": item.ocr_conf,
                "grounded": None,
                "has_file": bool(item.storage_path),
            }
            for item in docs
        ],
        "facts": [
            {
                "key": item.key,
                "value": _mask_value(item.key, item.value_json),
                "source_type": item.source_type,
                "grounded": item.grounded,
                "confidence": item.conf,
            }
            for item in facts
        ],
        "decisions": [
            {"scheme_id": item.scheme_id, "outcome": item.outcome, "rule_trace": item.rule_trace}
            for item in decisions
        ],
        "escalation": {
            "reason": _safe_text(escalation.reason),
            "evidence": sanitize_evidence(escalation.evidence),
        }
        if escalation
        else None,
    }


@app.post("/reviewer/{case_id}/resume")
async def reviewer_resume(
    case_id: UUID,
    payload: ReviewerResumeRequest,
    x_reviewer_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_reviewer(x_reviewer_token)
    if str(case_id) not in _services().runs:
        raise HTTPException(status_code=409, detail="case run is not resumable")
    session = _services().sessions()
    try:
        result = resume_case(
            build_graph(
                _services().runtime_factory(session, str(case_id)),
                checkpointer=_services().checkpointer,
            ),
            str(case_id),
            {"action": payload.action, "edited_facts": payload.edited_facts, "note": payload.note},
        )
        _services().runs[str(case_id)] = result
        _persist_run(case_id, result, session)
        log(
            session,
            case_id=case_id,
            actor="reviewer",
            event_type="reviewer.resume",
            summary=f"Reviewer selected {payload.action}",
            evidence={"action": payload.action, "edited_fact_keys": sorted(payload.edited_facts)},
        )
        session.commit()
        return {"case_id": str(case_id), "status": result.state.status}
    finally:
        session.close()


@app.get("/reviewer/{case_id}/audit")
async def reviewer_audit(
    case_id: UUID,
    x_reviewer_token: str | None = Header(default=None),
    session: Session = Depends(_session),
) -> list[dict[str, Any]]:
    _require_reviewer(x_reviewer_token)
    _case_or_404(case_id, session)
    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.ts)
    ).all()
    return [
        {
            "id": str(item.id),
            "ts": item.ts.isoformat(),
            "actor": item.actor,
            "event_type": item.event_type,
            "summary": _safe_text(item.summary),
            "evidence": sanitize_evidence(item.evidence),
            "confidence": item.confidence,
            "rationale": _safe_text(item.rationale or ""),
        }
        for item in rows
    ]


@app.post("/dev/seed")
async def dev_seed(
    background_tasks: BackgroundTasks, session: Session = Depends(_session)
) -> dict[str, Any]:
    if _services().settings.env == "prod":
        raise HTTPException(status_code=404, detail="not found")
    case = Case(
        language="en",
        channel="web",
        status="COLLECTING",
        consent_at=datetime.now(timezone.utc),
        intent_text="I need PM-Kisan help",
    )
    session.add(case)
    session.flush()
    for name in ("aadhaar.png", "land_record.png", "bank_passbook.png"):
        path = _services().storage.store(str(case.id), name, b"\x89PNG\r\n\x1a\nSAMPLE")
        metadata = _offline_metadata(name, path)
        _services().upload_metadata[path] = metadata
        session.add(
            Document(
                case_id=case.id,
                storage_path=path,
                doc_type=metadata["doc_type"],
                doc_type_conf=0.98,
                quality="good",
                quality_conf=0.95,
            )
        )
    session.commit()
    background_tasks.add_task(_run_case, str(case.id))
    return {"case_id": str(case.id)}
