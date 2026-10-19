"""Phase 2 persistence, audit, and storage acceptance tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from app.audit import AuditAppendOnlyError, audited, log
from app.db.models import AuditEvent, Base, Case, Document
from app.db.session import build_engine, build_session_factory, init_db
from app.integrations.storage import LocalStorageBackend, purge_expired
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def database(tmp_path: Path):
    engine = build_engine(f"sqlite:///{tmp_path / 'adhikaar.db'}")
    init_db(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        yield session
    engine.dispose()


def _case(session) -> Case:
    case = Case(language="ta", channel="telegram", channel_ref="synthetic-chat-001")
    session.add(case)
    session.flush()
    return case


def test_all_phase2_tables_and_case_document_round_trip(database) -> None:
    assert set(Base.metadata.tables) == {
        "cases",
        "documents",
        "facts",
        "decisions",
        "applications",
        "escalations",
        "messages",
        "audit_events",
    }

    case = _case(database)
    consent_time = datetime.now(timezone.utc)
    case.consent_at = consent_time
    document = Document(
        case_id=case.id,
        storage_path="synthetic-case-001/sample.png",
        doc_type="aadhaar",
        doc_type_conf=0.99,
        quality="good",
        quality_conf=0.98,
        ocr_text="SAMPLE — NOT A REAL DOCUMENT",
        ocr_conf=0.95,
    )
    database.add(document)
    database.commit()

    loaded = database.scalar(select(Case).where(Case.id == case.id))
    loaded_document = database.scalar(select(Document).where(Document.id == document.id))
    assert loaded is not None
    assert loaded.channel == "telegram"
    assert loaded.consent_at is not None
    assert loaded_document is not None
    assert loaded_document.case_id == case.id


def test_audit_log_redacts_ocr_and_identifiers(database) -> None:
    case = _case(database)
    event = log(
        database,
        case_id=case.id,
        actor="agent",
        event_type="ocr.completed",
        summary="Synthetic OCR completed",
        evidence={
            "ocr_text": "SAMPLE OCR 1234 5678 9012",
            "aadhaar_last4": "9012",
            "masked_value": "****9012",
            "rule_id": "owns_land",
        },
    )
    database.commit()

    assert event.evidence["ocr_text"] == "[REDACTED]"
    assert event.evidence["aadhaar_last4"] == "9012"
    assert event.evidence["masked_value"] == "****9012"
    assert "1234 5678 9012" not in str(event.evidence)


def test_audited_decorator_appends_event(database) -> None:
    case = _case(database)

    @audited("node.completed")
    def node(*, session, case_id):
        return {"ocr_text": "SAMPLE OCR MUST NOT SURVIVE"}

    node(session=database, case_id=case.id)
    database.commit()

    event = database.scalar(select(AuditEvent).where(AuditEvent.case_id == case.id))
    assert event is not None
    assert event.event_type == "node.completed"
    assert event.evidence["ocr_text"] == "[REDACTED]"


def test_audit_events_are_append_only_for_orm_and_sql(database) -> None:
    case = _case(database)
    event = log(
        database,
        case_id=case.id,
        actor="agent",
        event_type="case.started",
        summary="Started synthetic case",
    )
    database.commit()

    event.summary = "tampered"
    with pytest.raises(AuditAppendOnlyError):
        database.commit()
    database.rollback()

    with pytest.raises((AuditAppendOnlyError, IntegrityError)):
        database.execute(
            update(AuditEvent).where(AuditEvent.id == event.id).values(summary="tampered")
        )
        database.commit()
    database.rollback()

    with pytest.raises((AuditAppendOnlyError, IntegrityError)):
        database.execute(delete(AuditEvent).where(AuditEvent.id == event.id))
        database.commit()
    database.rollback()

    assert database.scalar(select(AuditEvent).where(AuditEvent.id == event.id)) is not None


def test_audit_append_only_trigger_rejects_direct_sql(database) -> None:
    case = _case(database)
    log(
        database,
        case_id=case.id,
        actor="agent",
        event_type="case.created",
        summary="Created synthetic case",
    )
    database.commit()

    with pytest.raises(IntegrityError):
        database.execute(text("DELETE FROM audit_events"))
        database.commit()
    database.rollback()


def test_local_storage_round_trip_and_path_traversal_rejection(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "private")
    storage_path = storage.store("synthetic-case-001", "document.png", b"synthetic bytes")

    assert storage.retrieve(storage_path) == b"synthetic bytes"
    storage.delete(storage_path)
    with pytest.raises(FileNotFoundError):
        storage.retrieve(storage_path)
    with pytest.raises(ValueError):
        storage.retrieve("../outside.txt")
    with pytest.raises(ValueError):
        storage.store("../escape", "document.png", b"nope")


def test_purge_expired_removes_file_but_keeps_document(database, tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "private")
    case = _case(database)
    storage_path = storage.store("synthetic-case-001", "document.png", b"old synthetic file")
    old_time = datetime.now(timezone.utc) - timedelta(days=8)
    document = Document(case_id=case.id, storage_path=storage_path, created_at=old_time)
    database.add(document)
    database.commit()

    purged = purge_expired(
        database,
        storage,
        retention_days=7,
        now=datetime.now(timezone.utc),
    )

    assert purged == 1
    assert not (storage.root / storage_path).exists()
    retained = database.scalar(select(Document).where(Document.id == document.id))
    assert retained is not None
    assert retained.storage_path is None
