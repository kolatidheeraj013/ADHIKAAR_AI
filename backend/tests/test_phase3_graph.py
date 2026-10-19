"""Phase 3 fake-backed acceptance scenarios A, B, C, D1, D2, and E."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.agents.graph import (
    GraphDependencies,
    build_graph,
    resume_case,
    run_case,
    sqlite_checkpointer,
)
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
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select


@pytest.fixture
def graph_context(tmp_path: Path):
    engine = build_engine(f"sqlite:///{tmp_path / 'graph.db'}")
    init_db(engine)
    factory = build_session_factory(engine)
    session = factory()
    case_id = uuid4()
    session.add(Case(id=case_id, language="ta", channel="web", status="RECEIVED"))
    session.commit()
    yield session, str(case_id)
    session.close()
    engine.dispose()


def _documents(include_land: bool = True, blurry: bool = False) -> list[str]:
    names = ["aadhaar.png", "bank_passbook.png"]
    if include_land:
        names.append("land_record_blurry.png" if blurry else "land_record.png")
    return names


def _runtime(
    session,
    *,
    llm=None,
    portal=None,
    classifier=None,
    notifier=None,
    include_tax: bool = True,
):
    docs = {
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
        speech=FakeSpeechClient(
            "நான் விவசாயி; PM-Kisan வேண்டும்",
            transcript,
        ),
        classifier=classifier or FakeDocClassifier(),
        ocr=FakeOCRClient(texts),
        llm=llm or FakeLLMClient(docs),
        retriever=FakeRetriever(),
        portal=portal or FakePortalClient(),
        notifier=notifier or FakeNotifier(),
    )


def _state(case_id: str, documents: list[str], *, voice: bool = True) -> CaseState:
    return CaseState(
        case_id=case_id,
        language="ta",
        channel="web",
        consent=True,
        voice_path="farmer.ogg" if voice else None,
        transcript=None if voice else "I'm a farmer, I want PM-Kisan",
        document_paths=documents,
    )


def test_scenario_a_auto_submits_with_full_audit(graph_context) -> None:
    session, case_id = graph_context
    runtime = _runtime(session)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    result = run_case(graph, _state(case_id, _documents()), thread_id=case_id)

    assert result.interrupts == []
    assert result.state.status == "COMPLETED"
    assert result.state.decisions["pm_kisan_mock"].outcome == "ELIGIBLE"
    assert result.state.confidence is not None and result.state.confidence >= 0.85
    assert result.state.applications["pm_kisan_mock"].status == "SUBMITTED"
    assert session.scalar(select(func.count(AuditEvent.id))) >= 12


def test_scenario_b_missing_document_then_reentry_submits(graph_context) -> None:
    session, case_id = graph_context
    runtime = _runtime(session)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    first = run_case(graph, _state(case_id, _documents(include_land=False)), thread_id=case_id)
    assert first.state.status == "NEEDS_DOCUMENTS"
    assert first.state.missing_documents["pm_kisan_mock"] == ["land_record"]
    assert not runtime.portal.submissions

    resumed = first.state.model_copy(deep=True)
    resumed.status = "NEEDS_DOCUMENTS"
    resumed.document_paths.append("land_record.png")
    second = run_case(graph, resumed, thread_id=f"{case_id}-documents")
    assert second.state.status == "COMPLETED"
    assert second.state.applications["pm_kisan_mock"].status == "SUBMITTED"


def test_scenario_c_blurry_document_escalates_then_reviewer_approves(graph_context) -> None:
    session, case_id = graph_context
    runtime = _runtime(session)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    first = run_case(graph, _state(case_id, _documents(blurry=True)), thread_id=case_id)
    assert first.interrupts
    assert first.state.status == "NEEDS_REVIEW"
    assert first.state.confidence is not None
    assert 0.60 <= first.state.confidence < 0.85

    second = resume_case(graph, case_id, {"action": "approve"})
    assert second.state.status == "COMPLETED"
    assert second.state.applications["pm_kisan_mock"].status == "SUBMITTED"


def test_scenario_d1_targeted_extraction_recovers_missing_ifsc(graph_context) -> None:
    session, case_id = graph_context
    llm = FakeLLMClient(
        document_facts={
            "land_record.png": {"land_owned_hectares": 2.5, "holder_type": "individual"},
            "aadhaar.png": {"applicant_name": "Synthetic Farmer", "aadhaar_last4": "9012"},
            "bank_passbook.png": {"bank_account_number": "SYNTHETIC-ACCOUNT"},
        },
        declaration_facts={"is_income_tax_payer": False},
        targeted_fields={("bank_passbook.png", "bank_ifsc"): "SYNTHETICIFSC"},
    )
    runtime = _runtime(session, llm=llm)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    result = run_case(graph, _state(case_id, _documents()), thread_id=case_id)

    assert result.state.status == "COMPLETED"
    assert result.state.facts["bank_ifsc"].value == "SYNTHETICIFSC"
    assert runtime.portal.submit_calls == 2


def test_scenario_d2_permanent_portal_rejection_escalates(graph_context) -> None:
    session, case_id = graph_context
    portal = FakePortalClient(fail_mode="reject_permanent")
    runtime = _runtime(session, portal=portal)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    first = run_case(graph, _state(case_id, _documents()), thread_id=case_id)
    assert first.interrupts
    assert first.state.status == "NEEDS_REVIEW"
    assert portal.submit_calls == 1

    second = resume_case(graph, case_id, {"action": "reject"})
    assert second.state.status == "FAILED_ESCALATED"


def test_scenario_d2_timeout_retries_twice_then_escalates(graph_context) -> None:
    session, case_id = graph_context
    portal = FakePortalClient(fail_mode="timeout")
    runtime = _runtime(session, portal=portal)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    first = run_case(graph, _state(case_id, _documents()), thread_id=case_id)

    assert first.interrupts
    assert first.state.status == "NEEDS_REVIEW"
    assert portal.submit_calls == 3
    assert first.state.applications["pm_kisan_mock"].attempts == 3


def test_scenario_e_missing_declaration_asks_and_resumes(graph_context) -> None:
    session, case_id = graph_context
    notifier = FakeNotifier()
    runtime = _runtime(session, notifier=notifier, include_tax=False)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    first = run_case(graph, _state(case_id, _documents()), thread_id=case_id)
    assert first.interrupts
    assert first.state.status == "NEEDS_INFO"
    assert first.state.pending_question is not None
    assert notifier.messages[-1]["kind"] == "question"
    assert len(notifier.messages[-1]["options"]) == 2

    second = resume_case(graph, case_id, {"value": False})
    assert second.state.status == "COMPLETED"
    assert second.state.applications["pm_kisan_mock"].status == "SUBMITTED"
    assert second.state.questions_asked <= 3


def test_sqlite_checkpointer_survives_graph_rebuild(graph_context, tmp_path: Path) -> None:
    session, case_id = graph_context
    runtime = _runtime(session, include_tax=False)
    checkpoint_path = tmp_path / "checkpoints.sqlite"

    with sqlite_checkpointer(checkpoint_path) as checkpointer:
        graph = build_graph(runtime, checkpointer=checkpointer)
        first = run_case(graph, _state(case_id, _documents()), thread_id=case_id)
        assert first.interrupts

    with sqlite_checkpointer(checkpoint_path) as checkpointer:
        rebuilt_graph = build_graph(runtime, checkpointer=checkpointer)
        second = resume_case(rebuilt_graph, case_id, {"value": False})

    assert second.state.status == "COMPLETED"
