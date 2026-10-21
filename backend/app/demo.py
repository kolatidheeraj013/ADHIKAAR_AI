"""Deterministic, synthetic-only Phase 10 demo scenarios.

The demo runner exercises the same LangGraph flow used by the backend, but keeps
its dependencies local and fake-backed so a cold-start demo does not need network
services, credentials, or real citizen data.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from app.agents.graph import GraphDependencies, build_graph, resume_case, run_case
from app.agents.state import CaseState
from app.db.models import AuditEvent, Case
from app.db.session import build_engine, build_session_factory, init_db
from app.integrations.fakes import (
    FakeDocClassifier,
    FakeLLMClient,
    FakeNotifier,
    FakeOCRClient,
    FakePortalClient,
    FakeRetriever,
    FakeSpeechClient,
)

SCENARIOS = ("A", "B", "C", "D1", "D2", "E")


def seed_manifest() -> dict[str, Any]:
    """Return the synthetic scenario inventory used by ``make seed``."""
    return {
        "synthetic_only": True,
        "scenarios": {
            "A": "Tamil voice, complete documents, auto-submit",
            "B": "Missing land record, document re-entry, then submit",
            "C": "Blurry land record, reviewer approval, then submit",
            "D1": "Missing IFSC, targeted extraction recovery",
            "D2": "Permanent portal rejection, escalation",
            "E": "Missing tax declaration, citizen question, then submit",
        },
        "documents": ["aadhaar.png", "land_record.png", "bank_passbook.png"],
        "thresholds": {"auto_submit": 0.85, "review": 0.60},
    }


@contextmanager
def _scenario_context() -> Iterator[tuple[Any, str]]:
    with TemporaryDirectory(prefix="adhikaar-phase10-") as directory:
        database_path = Path(directory) / "demo.db"
        engine = build_engine(f"sqlite:///{database_path}")
        init_db(engine)
        factory = build_session_factory(engine)
        session = factory()
        case_uuid = uuid4()
        case_id = str(case_uuid)
        session.add(Case(id=case_uuid, language="ta", channel="web", status="RECEIVED"))
        try:
            session.commit()
            yield session, case_id
        finally:
            session.rollback()
            session.close()
            engine.dispose()


def _documents(*, include_land: bool = True, blurry: bool = False) -> list[str]:
    names = ["aadhaar.png", "bank_passbook.png"]
    if include_land:
        names.append("land_record_blurry.png" if blurry else "land_record.png")
    return names


def _runtime(
    session: Any,
    *,
    llm: FakeLLMClient | None = None,
    portal: FakePortalClient | None = None,
    notifier: FakeNotifier | None = None,
    include_tax: bool = True,
) -> GraphDependencies:
    facts = {
        "land_record.png": {"land_owned_hectares": 2.5, "holder_type": "individual"},
        "land_record_blurry.png": {"land_owned_hectares": 2.5, "holder_type": "individual"},
        "aadhaar.png": {"applicant_name": "Synthetic Farmer", "aadhaar_last4": "9012"},
        "bank_passbook.png": {
            "bank_account_number": "SYNTHETIC-ACCOUNT",
            "bank_ifsc": "SYNTHETICIFSC",
        },
    }
    texts = {
        "land_record.png": "SAMPLE land_owned_hectares=2.5 holder_type=individual",
        "land_record_blurry.png": "SAMPLE land_owned_hectares=2.5 holder_type=individual",
        "aadhaar.png": "SAMPLE applicant_name=Synthetic Farmer aadhaar_last4=9012",
        "bank_passbook.png": "SAMPLE bank_account_number=SYNTHETIC-ACCOUNT bank_ifsc=SYNTHETICIFSC",
    }
    transcript = "I'm a farmer, I want PM-Kisan"
    if include_tax:
        transcript += "; nobody in my family pays income tax"
    return GraphDependencies(
        session=session,
        speech=FakeSpeechClient("நான் விவசாயி; PM-Kisan வேண்டும்", transcript),
        classifier=FakeDocClassifier(),
        ocr=FakeOCRClient(texts),
        llm=llm or FakeLLMClient(facts),
        retriever=FakeRetriever(),
        portal=portal or FakePortalClient(),
        notifier=notifier or FakeNotifier(),
        auto_submit_threshold=0.85,
        review_threshold=0.60,
    )


def _state(case_id: str, documents: list[str]) -> CaseState:
    return CaseState(
        case_id=case_id,
        language="ta",
        channel="web",
        consent=True,
        voice_path="farmer.ogg",
        document_paths=documents,
    )


def _evidence(session: Any, result: Any, *, scenario: str, portal_calls: int) -> dict[str, Any]:
    state = result.state
    application = next(iter(state.applications.values()), None)
    audit_count = session.scalar(
        select(func.count(AuditEvent.id)).where(AuditEvent.case_id == UUID(state.case_id))
    )
    return {
        "scenario": scenario,
        "status": state.status,
        "confidence": state.confidence,
        "portal_attempts": application.attempts if application else 0,
        "portal_reference": application.portal_ref if application else None,
        "portal_calls": portal_calls,
        "question_count": state.questions_asked,
        "missing_documents": state.missing_documents,
        "review_required": bool(result.interrupts),
        "audit_events": int(audit_count or 0),
        "message_count": len(state.messages),
        "synthetic_only": True,
    }


def _run(scenario: str) -> dict[str, Any]:
    with _scenario_context() as (session, case_id):
        portal = FakePortalClient(fail_mode="reject_permanent" if scenario == "D2" else "none")
        include_tax = scenario != "E"
        notifier = FakeNotifier()
        llm: FakeLLMClient | None = None
        if scenario == "D1":
            llm = FakeLLMClient(
                document_facts={
                    "land_record.png": {"land_owned_hectares": 2.5, "holder_type": "individual"},
                    "aadhaar.png": {"applicant_name": "Synthetic Farmer", "aadhaar_last4": "9012"},
                    "bank_passbook.png": {"bank_account_number": "SYNTHETIC-ACCOUNT"},
                },
                declaration_facts={"is_income_tax_payer": False},
                targeted_fields={("bank_passbook.png", "bank_ifsc"): "SYNTHETICIFSC"},
            )
        runtime = _runtime(
            session,
            llm=llm,
            portal=portal,
            notifier=notifier,
            include_tax=include_tax,
        )
        graph = build_graph(runtime, checkpointer=InMemorySaver())
        documents = _documents(include_land=scenario != "B", blurry=scenario == "C")
        first = run_case(graph, _state(case_id, documents), thread_id=case_id)

        result = first
        if scenario == "B":
            resumed = first.state.model_copy(deep=True)
            resumed.document_paths.append("land_record.png")
            result = run_case(graph, resumed, thread_id=f"{case_id}-documents")
        elif scenario == "C":
            result = resume_case(graph, case_id, {"action": "approve"})
        elif scenario == "E":
            result = resume_case(graph, case_id, {"value": False})
        elif scenario == "D2":
            # D2 intentionally ends in an open escalation after the permanent rejection.
            result = first

        evidence = _evidence(session, result, scenario=scenario, portal_calls=portal.submit_calls)
        evidence["notifier_messages"] = len(notifier.messages)
        return evidence


def run_scenario(scenario: str) -> dict[str, Any]:
    """Run one synthetic scenario and return acceptance evidence."""
    normalized = scenario.upper()
    if normalized not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; choose one of {', '.join(SCENARIOS)}")
    return _run(normalized)


def run_all() -> list[dict[str, Any]]:
    """Run all Phase 10 scenarios in deterministic order."""
    return [run_scenario(scenario) for scenario in SCENARIOS]
