"""PII-safe, append-only audit logging primitives."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from functools import wraps
from typing import Any, Callable, TypeVar
from uuid import UUID

from sqlalchemy import Engine, event
from sqlalchemy.orm import Session

from app.db.models import AuditEvent

_T = TypeVar("_T")
_LONG_DIGITS = re.compile(r"(?<!\d)(\d[\d\s-]{7,}\d)(?!\d)")
_SENSITIVE_KEYS = (
    "ocr",
    "raw_text",
    "full_text",
    "aadhaar",
    "account_number",
    "document_number",
    "id_number",
    "phone",
    "email",
    "address",
    "name",
)


class AuditAppendOnlyError(RuntimeError):
    """Raised when application code attempts to mutate an audit event."""


def mask_identifier(value: str) -> str:
    """Mask all but the last four digits of an identifier-like string."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 5:
        return "[REDACTED]"
    return "*" * (len(digits) - 4) + digits[-4:]


def sanitize_evidence(value: Any, *, key: str | None = None) -> Any:
    """Return JSON-safe evidence with raw identifiers and OCR removed."""
    normalized_key = key.lower() if key else ""
    if (
        normalized_key
        and "masked" not in normalized_key
        and "last4" not in normalized_key
        and any(marker in normalized_key for marker in _SENSITIVE_KEYS)
    ):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_evidence(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_evidence(item, key=key) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            if _LONG_DIGITS.search(value):
                return _LONG_DIGITS.sub(lambda match: mask_identifier(match.group(1)), value)
            if normalized_key == "masked_value" or "masked" in normalized_key:
                return value
        return value
    return str(value)


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return str(sanitize_evidence(value))


def log(
    session: Session,
    *,
    case_id: UUID | str,
    actor: str,
    event_type: str,
    summary: str,
    evidence: Mapping[str, Any] | None = None,
    confidence: float | None = None,
    rationale: str | None = None,
) -> AuditEvent:
    """Append one sanitized audit event to the current transaction."""
    normalized_case_id: UUID | str
    try:
        normalized_case_id = UUID(str(case_id))
    except (ValueError, AttributeError):
        normalized_case_id = case_id
    event_row = AuditEvent(
        case_id=normalized_case_id,
        actor=actor,
        event_type=event_type,
        summary=_sanitize_text(summary) or "",
        evidence=sanitize_evidence(evidence or {}),
        confidence=confidence,
        rationale=_sanitize_text(rationale),
    )
    session.add(event_row)
    session.flush()
    return event_row


def audited(
    event_type: str, *, summary: str | None = None
) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Decorate a node-like function so completion emits an audit event.

    The wrapped function must expose ``session`` and ``case_id`` parameters.
    Its mapping result is used only as evidence and is sanitized before storage.
    """

    def decorator(function: Callable[..., _T]) -> Callable[..., _T]:
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> _T:
            bound = signature.bind_partial(*args, **kwargs)
            result = function(*args, **kwargs)
            session = bound.arguments.get("session")
            case_id = bound.arguments.get("case_id")
            if not isinstance(session, Session) or case_id is None:
                raise RuntimeError("audited functions require session and case_id parameters")
            evidence = result if isinstance(result, Mapping) else {}
            log(
                session,
                case_id=case_id,
                actor="agent",
                event_type=event_type,
                summary=summary or f"{function.__name__} completed",
                evidence=evidence,
            )
            return result

        return wrapped

    return decorator


def audit_node(
    event_type: str, *, summary: str | None = None
) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Explicit alias for the decorator used by graph nodes."""
    return audited(event_type, summary=summary)


@event.listens_for(AuditEvent, "before_update", propagate=True)
def _reject_audit_update(*_: Any) -> None:
    raise AuditAppendOnlyError("audit_events is append-only; updates are forbidden")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def _reject_audit_delete(*_: Any) -> None:
    raise AuditAppendOnlyError("audit_events is append-only; deletes are forbidden")


def install_append_only_guards(engine: Engine) -> None:
    """Install a database-level guard where the local SQLite engine supports it."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
              SELECT RAISE(ABORT, 'audit_events is append-only');
            END;
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN
              SELECT RAISE(ABORT, 'audit_events is append-only');
            END;
            """
        )
