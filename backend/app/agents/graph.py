"""LangGraph walking skeleton with deterministic integration fakes."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.state import (
    ApplicationResult,
    CaseState,
    CitizenMessage,
    Decision,
    DocumentResult,
    Escalation,
    Fact,
    Question,
)
from app.audit import log
from app.db.models import Message
from app.integrations.interfaces import (
    DocClassifier,
    LLMClient,
    Notifier,
    OCRClient,
    PortalClient,
    Retriever,
    SpeechClient,
    StorageBackend,
)
from app.rules.engine import DecisionOutcome, evaluate, load_scheme, load_schemes


@dataclass
class GraphDependencies:
    session: Session
    speech: SpeechClient
    classifier: DocClassifier
    ocr: OCRClient
    llm: LLMClient
    retriever: Retriever
    portal: PortalClient
    notifier: Notifier
    storage: StorageBackend | None = None
    auto_submit_threshold: float = 0.85
    review_threshold: float = 0.60
    audit_event_ids: list[str] = field(default_factory=list)


class GraphRun(BaseModel):
    state: CaseState
    interrupts: list[Any] = []


def _as_state(value: CaseState | dict[str, Any]) -> CaseState:
    return value if isinstance(value, CaseState) else CaseState.model_validate(value)


def _return(state: CaseState) -> dict[str, Any]:
    return state.model_dump(mode="json")


def _audit_node(
    runtime: GraphDependencies,
    name: str,
    state: CaseState,
    duration_ms: float = 0.0,
) -> None:
    event = log(
        runtime.session,
        case_id=state.case_id,
        actor="agent",
        event_type=f"node.{name}",
        summary=f"{name} node executed in {duration_ms}ms" if duration_ms > 0 else f"{name} node executed",
        evidence={
            "node": name,
            "status": state.status,
            "scheme": state.candidate_schemes[:1],
            "duration_ms": duration_ms,
        },
    )
    runtime.audit_event_ids.append(str(event.id))


def _portal_audit(
    runtime: GraphDependencies,
    state: CaseState,
    event_type: str,
    summary: str,
    evidence: dict[str, Any],
) -> None:
    if runtime.session is None:
        return
    event = log(
        runtime.session,
        case_id=state.case_id,
        actor="agent",
        event_type=event_type,
        summary=summary,
        evidence=evidence,
    )
    runtime.audit_event_ids.append(str(event.id))


def _notify(
    runtime: GraphDependencies,
    state: CaseState,
    message: CitizenMessage,
) -> None:
    """Persist an outgoing message before handing it to the notifier.

    Telegram callbacks use this database ID for answer correlation. A queued
    Telegram delivery remains ``delivered=False`` until its worker reports
    success; local/fake notifiers return ``True`` immediately.
    """
    message_id: str | None = None
    message_row: Message | None = None
    if runtime.session is not None:
        message_row = Message(
            case_id=UUID(state.case_id),
            direction="out",
            kind=message.kind,
            language=message.language,
            text=str(message.text),
            payload={"options": message.options},
            delivered=False,
        )
        runtime.session.add(message_row)
        runtime.session.flush()
        message_id = str(message_row.id)
    delivered = runtime.notifier.notify(
        state.case_id,
        state.language,
        message.kind,
        message.text,
        message.options,
        message_id=message_id,
    )
    if message_row is not None and delivered is True:
        message_row.delivered = True


def _masked_fact_value(key: str, value: Any) -> Any:
    if key == "applicant_name":
        return "[REDACTED]"
    if key in {"aadhaar_last4", "bank_account_number", "bank_ifsc"}:
        digits = "".join(character for character in str(value) if character.isdigit())
        return f"***{digits[-4:]}" if digits else "[REDACTED]"
    return value


def _recovery_evidence(state: CaseState, scheme_id: str, error: dict[str, Any]) -> dict[str, Any]:
    decision = state.decisions.get(scheme_id)
    application = state.applications.get(scheme_id)
    return {
        "document_ids": [document.doc_id for document in state.documents],
        "masked_facts": {
            key: _masked_fact_value(key, fact.value) for key, fact in state.facts.items()
        },
        "rule_trace": decision.rule_trace if decision else [],
        "portal_error": error,
        "attempts": application.attempts if application else 0,
        "tried": dict(state.retries),
    }


def _node(
    runtime: GraphDependencies,
    name: str,
    function: Callable[[CaseState, GraphDependencies], CaseState],
):
    def wrapped(value: CaseState | dict[str, Any]) -> dict[str, Any]:
        state = _as_state(value)
        start_time = time.perf_counter()
        next_state = function(state, runtime)
        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        _audit_node(runtime, name, next_state, duration_ms=duration_ms)
        return _return(next_state)

    return wrapped


def intake(state: CaseState, runtime: GraphDependencies) -> CaseState:
    if not state.consent:
        raise ValueError("consent is required before intake")
    if not state.voice_path and not state.transcript:
        raise ValueError("a voice path or typed transcript is required")
    if not state.document_paths:
        raise ValueError("at least one document is required")
    state.reentry_from_documents = state.status == "NEEDS_DOCUMENTS"
    state.status = "PROCESSING"
    state.route = ""
    return state


def transcribe(state: CaseState, runtime: GraphDependencies) -> CaseState:
    if state.voice_path:
        state.transcript = runtime.speech.transcribe(state.voice_path, state.language)
    state.transcript_en = state.transcript
    return state


def classify_docs(state: CaseState, runtime: GraphDependencies) -> CaseState:
    existing = {document.path for document in state.documents}
    for path in state.document_paths:
        if path in existing:
            continue
        result = runtime.classifier.classify(path)
        state.documents.append(
            DocumentResult(
                doc_id=path,
                path=path,
                doc_type=result["doc_type"],
                doc_type_conf=float(result.get("doc_type_conf", 0.0)),
                quality=result.get("quality", "too_dark"),
                quality_conf=float(result.get("quality_conf", 0.0)),
            )
        )
    return state


def ocr(state: CaseState, runtime: GraphDependencies) -> CaseState:
    for document in state.documents:
        if document.ocr_text:
            continue
        result = runtime.ocr.ocr(document.path)
        document.ocr_text = str(result.get("text", ""))
        document.ocr_conf = float(result.get("confidence", 0.0))
    return state


def _all_fact_keys() -> tuple[list[str], list[str]]:
    document_keys: list[str] = []
    declaration_keys: list[str] = []
    for scheme in load_schemes().values():
        for fact in scheme.facts:
            target = declaration_keys if fact.source == "declaration" else document_keys
            if fact.key not in target:
                target.append(fact.key)
        for payload_field in scheme.payload_fields:
            if payload_field.key not in document_keys:
                document_keys.append(payload_field.key)
    return document_keys, declaration_keys


def _grounded(value: Any, text: str) -> bool:
    normalized_text = "".join(str(text).lower().split())
    normalized_value = "".join(str(value).lower().split())
    if normalized_value in normalized_text:
        return True
    digits = "".join(char for char in normalized_value if char.isdigit())
    return bool(digits) and digits in "".join(char for char in normalized_text if char.isdigit())


def extract_facts(state: CaseState, runtime: GraphDependencies) -> CaseState:
    document_keys, declaration_keys = _all_fact_keys()
    for document in state.documents:
        extracted = runtime.llm.extract_facts(
            document.ocr_text, "document", document.doc_id, document_keys
        )
        for key, value in extracted.items():
            state.facts[key] = Fact(
                key=key,
                value=value,
                source_type="document",
                source_doc_id=document.doc_id,
                grounded=_grounded(value, document.ocr_text),
                conf=document.ocr_conf,
            )
    if state.transcript_en:
        extracted = runtime.llm.extract_facts(
            state.transcript_en, "declaration", None, declaration_keys
        )
        for key, value in extracted.items():
            state.facts[key] = Fact(
                key=key,
                value=value,
                source_type="declaration",
                grounded=None,
                conf=0.8,
            )
    return state


def plan(state: CaseState, runtime: GraphDependencies) -> CaseState:
    results = runtime.retriever.retrieve(state.transcript_en or state.transcript or "")
    loaded_schemes = load_schemes()
    candidates: list[str] = []
    for result in results:
        scheme_id = result.get("scheme_id")
        if not scheme_id:
            source = str(result.get("source", ""))
            scheme_id = Path(source.split("#", 1)[0]).stem
        if scheme_id in loaded_schemes and scheme_id not in candidates:
            candidates.append(str(scheme_id))
    state.candidate_schemes = candidates
    if not state.candidate_schemes:
        state.candidate_schemes = ["pm_kisan_mock"]
    return state


def check_docs(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme_id = state.candidate_schemes[0]
    scheme = load_scheme(Path(__file__).parents[1] / "rules" / "schemes" / f"{scheme_id}.yaml")
    provided = {document.doc_type for document in state.documents if document.quality != "too_dark"}
    missing = [document for document in scheme.required_documents if document not in provided]
    state.missing_documents[scheme_id] = missing
    state.route = "explain" if missing else "eligibility"
    if missing:
        state.status = "NEEDS_DOCUMENTS"
    return state


def _primary_scheme(state: CaseState):
    if not state.candidate_schemes:
        raise ValueError("plan must select a scheme before eligibility")
    scheme_id = state.candidate_schemes[0]
    path = Path(__file__).parents[1] / "rules" / "schemes" / f"{scheme_id}.yaml"
    return load_scheme(path)


def eligibility(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme = _primary_scheme(state)
    decision = evaluate(scheme, state.facts)
    state.confidence = _confidence(state)
    state.decisions[scheme.scheme_id] = Decision(
        scheme_id=scheme.scheme_id,
        outcome=decision.outcome.value,
        rule_trace=[trace.model_dump(mode="json") for trace in decision.trace],
    )
    if decision.outcome is DecisionOutcome.NOT_ELIGIBLE:
        state.status = "NOT_ELIGIBLE"
        state.route = "explain"
        return state
    if decision.outcome is DecisionOutcome.ELIGIBLE:
        state.route = "verify"
        return state

    missing = {fact.key: fact for fact in scheme.facts if fact.key not in state.facts}
    declaration_missing = [fact for fact in missing.values() if fact.source == "declaration"]
    document_missing = [fact for fact in missing.values() if fact.source != "declaration"]
    if declaration_missing and not document_missing and state.questions_asked < 3:
        state.route = "ask_info"
    elif document_missing and not declaration_missing:
        sources = {fact.source for fact in document_missing}
        first_request = any(state.retries.get(f"reupload:{source}", 0) == 0 for source in sources)
        if first_request:
            for source in sources:
                state.retries[f"reupload:{source}"] = 1
            state.status = "NEEDS_DOCUMENTS"
            state.route = "explain"
        else:
            state.route = "escalate"
    else:
        state.route = "escalate"
    return state


def ask_info(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme = _primary_scheme(state)
    missing = next(
        (
            fact
            for fact in scheme.facts
            if fact.source == "declaration" and fact.key not in state.facts
        ),
        None,
    )
    if missing is None:
        state.route = "eligibility"
        return state
    state.questions_asked += 1
    state.status = "NEEDS_INFO"
    state.pending_question = Question(
        key=missing.key,
        text=missing.question or f"Please answer: {missing.key}",
        options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}],
    )
    question_message = CitizenMessage(
        kind="question",
        language=state.language,
        text=state.pending_question.text,
        options=state.pending_question.options,
    )
    state.messages.append(question_message)
    _notify(runtime, state, question_message)
    answer = interrupt(state.pending_question.model_dump(mode="json"))
    if isinstance(answer, dict):
        value = answer.get("value", answer.get("option"))
    else:
        value = answer
    if not isinstance(value, bool):
        raise ValueError("declaration answer must be boolean")
    state.facts[missing.key] = Fact(
        key=missing.key,
        value=value,
        source_type="declaration",
        grounded=None,
        conf=0.8,
    )
    state.pending_question = None
    state.status = "PROCESSING"
    state.route = "eligibility"
    return state


def _confidence(state: CaseState) -> float:
    scheme = _primary_scheme(state)
    docs_by_type = {document.doc_type: document for document in state.documents}
    doc_scores = []
    for required in scheme.required_documents:
        document = docs_by_type.get(required)
        if document is None:
            doc_scores.append(0.0)
            continue
        quality_factor = 1.0 if document.quality == "good" else 0.6
        doc_scores.append(document.doc_type_conf * quality_factor)
    doc_conf = min(doc_scores) if doc_scores else 0.0
    supporting_docs = [document for document in state.documents if document.ocr_text]
    ocr_conf = (
        sum(document.ocr_conf for document in supporting_docs) / len(supporting_docs)
        if supporting_docs
        else 0.0
    )
    scheme_fact_keys = {fact.key for fact in scheme.facts}
    grounding_scores = []
    for key in scheme_fact_keys:
        fact = state.facts.get(key)
        if fact is None:
            grounding_scores.append(0.0)
        elif fact.source_type == "reviewer" or fact.grounded is True:
            grounding_scores.append(1.0)
        elif fact.source_type == "declaration":
            grounding_scores.append(0.8)
        else:
            grounding_scores.append(0.5)
    grounding_conf = min(grounding_scores) if grounding_scores else 0.0
    return round(0.4 * doc_conf + 0.3 * ocr_conf + 0.3 * grounding_conf, 4)


def verify(state: CaseState, runtime: GraphDependencies) -> CaseState:
    state.confidence = _confidence(state)
    if state.human_approved or (state.confidence >= runtime.auto_submit_threshold):
        state.route = "act"
    elif state.confidence >= runtime.review_threshold:
        state.route = "escalate"
    elif state.retries.get("confidence_reupload", 0) == 0:
        state.retries["confidence_reupload"] = 1
        state.status = "NEEDS_DOCUMENTS"
        state.route = "explain"
    else:
        state.route = "escalate"
    return state


def act(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme = _primary_scheme(state)
    decision = state.decisions[scheme.scheme_id]
    if decision.outcome != "ELIGIBLE":
        raise ValueError("act is guarded: latest decision is not ELIGIBLE")
    payload: dict[str, Any] = {}
    for payload_field in scheme.payload_fields:
        fact = state.facts.get(payload_field.key)
        if fact is not None:
            payload[payload_field.key] = fact.value
    result = runtime.portal.submit(scheme.scheme_id, payload)
    previous = state.applications.get(scheme.scheme_id)
    attempts = (previous.attempts if previous else 0) + 1
    if result.get("ok"):
        state.applications[scheme.scheme_id] = ApplicationResult(
            scheme_id=scheme.scheme_id,
            status="PENDING",
            portal_ref=result.get("portal_ref"),
            attempts=attempts,
        )
        state.last_portal_error = None
    else:
        error = dict(result.get("error", {"kind": "unknown", "message": "MOCK failure"}))
        state.applications[scheme.scheme_id] = ApplicationResult(
            scheme_id=scheme.scheme_id,
            status="FAILED",
            attempts=attempts,
            error=error,
        )
        state.last_portal_error = error
    _portal_audit(
        runtime,
        state,
        "portal.submit.attempt",
        "Portal submission attempt completed",
        {
            "scheme": scheme.scheme_id,
            "attempt": attempts,
            "payload_fields": sorted(payload),
            "ok": bool(result.get("ok")),
            "portal_error": state.last_portal_error,
        },
    )
    state.route = "verify_submission"
    return state


def verify_submission(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme = _primary_scheme(state)
    application = state.applications[scheme.scheme_id]
    if application.status == "PENDING" and application.portal_ref:
        result = runtime.portal.verify(application.portal_ref)
        if result.get("ok"):
            application.status = "SUBMITTED"
            state.status = "SUBMITTED"
            state.route = "explain"
            _portal_audit(
                runtime,
                state,
                "portal.verify.attempt",
                "Portal verification attempt completed",
                {"scheme": scheme.scheme_id, "portal_ref": application.portal_ref, "ok": True},
            )
            return state
        state.last_portal_error = dict(result.get("error", {"kind": "unknown"}))
        _portal_audit(
            runtime,
            state,
            "portal.verify.attempt",
            "Portal verification attempt completed",
            {
                "scheme": scheme.scheme_id,
                "portal_ref": application.portal_ref,
                "ok": False,
                "portal_error": state.last_portal_error,
            },
        )
    state.route = "recover"
    return state


def recover(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme = _primary_scheme(state)
    error = state.last_portal_error or {}
    kind = error.get("kind")
    if kind in {"timeout", "transient"} or str(error.get("code", "")).startswith("http_5"):
        key = f"submit:{scheme.scheme_id}"
        retries = state.retries.get(key, 0)
        if retries < 2:
            state.retries[key] = retries + 1
            time.sleep(0.05 * (2**retries))
            state.route = "act"
            return state
    elif kind == "validation" and error.get("code") == "missing_field":
        field_name = str(error.get("field", ""))
        key = f"autofix:{field_name}"
        if state.retries.get(key, 0) == 0:
            field = next((item for item in scheme.payload_fields if item.key == field_name), None)
            if field is not None:
                source_doc = next(
                    (document for document in state.documents if document.doc_type == field.source),
                    None,
                )
                existing = state.facts.get(field_name)
                if existing is not None:
                    state.retries[key] = 1
                    state.route = "act"
                    return state
                if source_doc is not None:
                    value = runtime.llm.extract_field(
                        source_doc.ocr_text, field_name, source_doc.doc_id
                    )
                    if value is not None:
                        state.facts[field_name] = Fact(
                            key=field_name,
                            value=value,
                            source_type="document",
                            source_doc_id=source_doc.doc_id,
                            grounded=_grounded(value, source_doc.ocr_text),
                            conf=source_doc.ocr_conf,
                        )
                        state.retries[key] = 1
                        state.route = "act"
                        return state
    if kind == "permanent":
        reason = (
            "The MOCK portal permanently rejected the application "
            f"({error.get('code', 'unknown error')})."
        )
    elif kind in {"timeout", "transient"} or str(error.get("code", "")).startswith("http_5"):
        reason = (
            "The MOCK portal remained unavailable after the initial submission and two retries."
        )
    else:
        reason = (
            "The MOCK portal rejected the application and the one automatic field fix "
            "did not resolve it."
        )
    state.status = "FAILED_ESCALATED"
    state.escalation = Escalation(
        reason=f"{reason} A human reviewer needs to complete the application.",
        evidence=_recovery_evidence(state, scheme.scheme_id, error),
    )
    state.route = "escalate"
    return state


def _citizen_outcome(state: CaseState, decision: Decision | None) -> str:
    """Return the deterministic rule outcome without hiding review status."""
    if decision is not None:
        return decision.outcome
    return "UNDETERMINED"


def _confidence_summary(
    confidence: float | None,
    runtime: GraphDependencies,
) -> str | None:
    if confidence is None:
        return None
    if confidence >= runtime.auto_submit_threshold:
        band = "HIGH band"
    elif confidence >= runtime.review_threshold:
        band = "REVIEW band"
    else:
        band = "LOW band"
    return f"Confidence: {confidence:.1%} ({band})"


def _rule_reasons(trace: list[dict[str, Any]]) -> str:
    if not trace:
        return (
            "Rule reasons: eligibility rules have not run because required information "
            "or documents are missing."
        )
    failed = [
        str(item.get("reason", "Rule failed.")) for item in trace if item.get("status") == "failed"
    ]
    unknown = [
        str(item.get("reason", "More information is required."))
        for item in trace
        if item.get("status") == "unknown"
    ]
    reasons = failed or unknown
    if not reasons:
        return "Rule reasons: all recorded rules passed."
    label = "Rule reasons" if failed else "Rule reasons needing review"
    return label + ":\n" + "\n".join(f"- {reason}" for reason in reasons)


def _result_text(state: CaseState, runtime: GraphDependencies) -> str:
    scheme_id = state.candidate_schemes[0] if state.candidate_schemes else "pm_kisan_mock"
    scheme = load_scheme(Path(__file__).parents[1] / "rules" / "schemes" / f"{scheme_id}.yaml")
    decision = state.decisions.get(scheme_id)
    outcome = _citizen_outcome(state, decision)
    trace = decision.rule_trace if decision else []
    confidence = _confidence_summary(state.confidence, runtime)
    sections = [
        "MOCK / synthetic case result",
        f"Scheme: {scheme.name} ({scheme.scheme_id})",
        f"Outcome: {outcome}",
        f"Case status: {state.status}",
        f"MOCK benefit: {scheme.benefit}",
        _rule_reasons(trace),
        _portal_summary(state, scheme_id),
        _next_step(state, scheme_id, outcome),
    ]
    if confidence:
        sections.insert(4, confidence)
    if state.status == "COMPLETED":
        application = state.applications.get(scheme_id)
        if application and application.status == "SUBMITTED" and application.portal_ref:
            sections.append(f"Submitted successfully. MOCK reference: {application.portal_ref}")
    return "\n".join(sections)


def _portal_summary(state: CaseState, scheme_id: str) -> str:
    application = state.applications.get(scheme_id)
    if application is None:
        return "Portal submission: NOT_ATTEMPTED."
    if application.status == "SUBMITTED" and application.portal_ref:
        return f"Portal submission: SUBMITTED (MOCK reference: {application.portal_ref})"
    if application.status == "PENDING":
        return "Portal submission: PENDING at the MOCK portal."
    return "Portal submission: FAILED at the MOCK portal."


def _next_step(state: CaseState, scheme_id: str, outcome: str) -> str:
    if state.status == "NEEDS_DOCUMENTS":
        missing = state.missing_documents.get(scheme_id, [])
        documents = ", ".join(missing) if missing else "the required document(s)"
        return f"Next step: upload the missing or clearer MOCK document(s): {documents}."
    if state.status == "FAILED_ESCALATED":
        return "Next step: a human reviewer must complete this MOCK application."
    if state.status == "NEEDS_REVIEW":
        return "Next step: a human reviewer must review this MOCK case."
    if outcome == "NEEDS_REVIEW":
        return "Next step: a human reviewer must review this MOCK case."
    if outcome == "NOT_ELIGIBLE":
        return "Next step: no portal submission was made because the rules found an exclusion."
    return "Next step: keep the MOCK portal reference for follow-up."


def escalate(state: CaseState, runtime: GraphDependencies) -> CaseState:
    terminal_portal_failure = state.status == "FAILED_ESCALATED"
    first_escalation = state.escalation is None
    send_review_update = first_escalation or terminal_portal_failure
    if first_escalation:
        state.escalation = Escalation(
            reason=(
                "Confidence is in the review band"
                if state.confidence is not None
                else "The agent needs human review"
            ),
            evidence={
                "confidence": state.confidence,
                "portal_error": state.last_portal_error,
                "scheme": state.candidate_schemes[:1],
            },
        )
    escalation = state.escalation
    assert escalation is not None
    state.status = "NEEDS_REVIEW"
    if send_review_update:
        review_message = CitizenMessage(
            kind="result",
            language=state.language,
            text=_result_text(state, runtime),
        )
        state.messages.append(review_message)
        _notify(runtime, state, review_message)
    answer = interrupt(
        {
            "reason": escalation.reason,
            "evidence": escalation.evidence,
            "options": ["approve", "reject", "request_docs"],
        }
    )
    action = answer if isinstance(answer, dict) else {"action": answer}
    action_name = action.get("action")
    if action_name == "approve":
        scheme_id = state.candidate_schemes[0]
        latest = state.decisions.get(scheme_id)
        edited_facts = action.get("edited_facts") or {}
        if latest is None or (latest.outcome != "ELIGIBLE" and not edited_facts):
            raise ValueError("approve requires an eligible decision or edited_facts")
        for key, value in edited_facts.items():
            state.facts[key] = Fact(
                key=key,
                value=value,
                source_type="reviewer",
                grounded=None,
                conf=1.0,
            )
        state.human_approved = True
        escalation.status = "RESOLVED"
        escalation.resolution = "approved"
        state.status = "PROCESSING"
        state.route = "eligibility" if edited_facts else "act"
    elif action_name == "reject":
        escalation.status = "RESOLVED"
        escalation.resolution = "rejected"
        state.status = "FAILED_ESCALATED" if terminal_portal_failure else "NOT_ELIGIBLE"
        state.route = "explain"
    elif action_name == "request_docs":
        escalation.resolution = "request_docs"
        state.status = "NEEDS_DOCUMENTS"
        state.route = "explain"
    else:
        raise ValueError("review action must be approve, reject, or request_docs")
    return state


def explain(state: CaseState, runtime: GraphDependencies) -> CaseState:
    scheme_id = state.candidate_schemes[0] if state.candidate_schemes else "pm_kisan_mock"
    decision = state.decisions.get(scheme_id)
    outcome = _citizen_outcome(state, decision)
    trace = decision.rule_trace if decision else []
    if state.status == "SUBMITTED":
        state.status = "COMPLETED"
    text = _result_text(state, runtime)
    citation_query = " ".join(
        [state.transcript_en or state.transcript or "", outcome]
        + [str(item.get("reason", "")) for item in trace]
    ).strip()
    citations = runtime.retriever.retrieve(citation_query, k=2)
    sources = list(
        dict.fromkeys(str(item.get("source", "")) for item in citations if item.get("source"))
    )
    if sources:
        text = f"{text}\n\nMOCK rulebook source: " + ", ".join(sources)
    message = CitizenMessage(kind="result", language=state.language, text=text)
    state.messages.append(message)
    _notify(runtime, state, message)
    state.route = "end"
    return state


def _route(state: CaseState) -> str:
    return state.route


def build_graph(
    runtime: GraphDependencies,
    *,
    checkpointer: Any | None = None,
):
    """Build the dependency-injected LangGraph graph for one runtime."""
    builder = StateGraph(CaseState)
    functions = {
        "intake": intake,
        "transcribe": transcribe,
        "classify_docs": classify_docs,
        "ocr": ocr,
        "extract_facts": extract_facts,
        "plan": plan,
        "check_docs": check_docs,
        "eligibility": eligibility,
        "ask_info": ask_info,
        "verify": verify,
        "act": act,
        "verify_submission": verify_submission,
        "recover": recover,
        "escalate": escalate,
        "explain": explain,
    }
    for name, function in functions.items():
        builder.add_node(name, _node(runtime, name, function))

    builder.add_edge(START, "intake")
    builder.add_conditional_edges(
        "intake",
        lambda value: "classify_docs" if _as_state(value).reentry_from_documents else "transcribe",
        {"transcribe": "transcribe", "classify_docs": "classify_docs"},
    )
    builder.add_edge("transcribe", "classify_docs")
    builder.add_edge("classify_docs", "ocr")
    builder.add_edge("ocr", "extract_facts")
    builder.add_edge("extract_facts", "plan")
    builder.add_edge("plan", "check_docs")
    builder.add_conditional_edges(
        "check_docs", _route, {"explain": "explain", "eligibility": "eligibility"}
    )
    builder.add_conditional_edges(
        "eligibility",
        _route,
        {"explain": "explain", "ask_info": "ask_info", "escalate": "escalate", "verify": "verify"},
    )
    builder.add_edge("ask_info", "eligibility")
    builder.add_conditional_edges(
        "verify",
        _route,
        {"act": "act", "escalate": "escalate", "explain": "explain"},
    )
    builder.add_edge("act", "verify_submission")
    builder.add_conditional_edges(
        "verify_submission", _route, {"explain": "explain", "recover": "recover"}
    )
    builder.add_conditional_edges("recover", _route, {"act": "act", "escalate": "escalate"})
    builder.add_conditional_edges(
        "escalate",
        _route,
        {"act": "act", "eligibility": "eligibility", "explain": "explain"},
    )
    builder.add_edge("explain", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


@contextmanager
def sqlite_checkpointer(path: str | Path):
    """Yield a persistent SQLite checkpointer for local resumable runs."""
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver


def run_case(graph: Any, state: CaseState, *, thread_id: str | None = None) -> GraphRun:
    """Start a case with a stable LangGraph thread id."""
    config = {"configurable": {"thread_id": thread_id or state.case_id}}
    result = graph.invoke(_return(state), config)
    interrupts = result.get("__interrupt__", []) if isinstance(result, dict) else []
    values = {key: value for key, value in result.items() if key != "__interrupt__"}
    normalized_state = CaseState.model_validate(values)
    if interrupts:
        payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
        if isinstance(payload, dict) and "key" in payload:
            normalized_state.status = "NEEDS_INFO"
            normalized_state.pending_question = Question.model_validate(payload)
        elif isinstance(payload, dict) and "reason" in payload:
            normalized_state.status = "NEEDS_REVIEW"
            normalized_state.escalation = Escalation(
                reason=str(payload["reason"]), evidence=dict(payload.get("evidence") or {})
            )
    return GraphRun(state=normalized_state, interrupts=list(interrupts))


def resume_case(graph: Any, case_id: str, answer: Any) -> GraphRun:
    """Resume an interrupted citizen or reviewer interaction."""
    result = graph.invoke(Command(resume=answer), {"configurable": {"thread_id": case_id}})
    interrupts = result.get("__interrupt__", []) if isinstance(result, dict) else []
    values = {key: value for key, value in result.items() if key != "__interrupt__"}
    return GraphRun(state=CaseState.model_validate(values), interrupts=list(interrupts))
