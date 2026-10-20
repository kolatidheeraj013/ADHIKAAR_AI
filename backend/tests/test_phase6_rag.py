"""Zero-network acceptance checks for Phase 6 rulebook RAG."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.agents.graph import GraphDependencies, explain, plan
from app.agents.state import CaseState
from app.integrations.fakes import FakeLLMClient, FakeNotifier
from app.rag.ingest import ingest_rulebooks, load_rulebook_chunks
from app.rag.retriever import RulebookRetriever
from app.rules.engine import DecisionOutcome, evaluate, load_scheme

PROJECT_ROOT = Path(__file__).parents[2]
RULEBOOKS = PROJECT_ROOT / "data" / "rulebooks"


def test_scheme_discovery_returns_right_scheme_in_top_two(tmp_path: Path) -> None:
    retriever = ingest_rulebooks(
        RULEBOOKS,
        tmp_path / "index",
        use_chroma=False,
        force_fallback=True,
    )

    results = retriever.retrieve("I am a student and need education scholarship support", k=2)

    assert len(results) == 2
    assert results[0]["source"] == "state_scholarship_mock.md"


def test_heading_chunks_keep_source_and_heading_citations(tmp_path: Path) -> None:
    chunks = load_rulebook_chunks(RULEBOOKS)
    assert {chunk["scheme_id"] for chunk in chunks} == {
        "pm_kisan_mock",
        "state_scholarship_mock",
    }
    assert any(
        chunk["source"] == "pm_kisan_mock.md"
        and chunk["heading"] == "Required documents (MOCK)"
        and "land record" in chunk["text"]
        for chunk in chunks
    )

    retriever = RulebookRetriever(chunks, chroma_path=tmp_path / "index", use_chroma=False)
    result = retriever.retrieve("farmer land record", k=1)[0]
    assert result["source"] == "pm_kisan_mock.md"
    assert "land" in result["text"].lower()
    assert set(result) == {"text", "source", "score"}


def test_retrieval_limits_k_and_persists_lexical_fallback(tmp_path: Path) -> None:
    index_path = tmp_path / "index"
    original = ingest_rulebooks(
        RULEBOOKS,
        index_path,
        use_chroma=False,
        force_fallback=True,
    )
    assert len(original.retrieve("MOCK scheme", k=1)) == 1
    assert (index_path / "rulebooks.lexical.json").is_file()

    reopened = RulebookRetriever.from_persisted(index_path, use_chroma=False)
    assert reopened.retrieve("farmer land", k=3)
    assert len(reopened.retrieve("farmer land", k=0)) == 0


def test_empty_directory_is_safe_and_missing_directory_is_clear(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    empty = ingest_rulebooks(
        empty_dir,
        tmp_path / "empty-index",
        use_chroma=False,
        force_fallback=True,
    )
    assert empty.retrieve("anything") == []

    with pytest.raises(FileNotFoundError, match="rulebook directory does not exist"):
        load_rulebook_chunks(tmp_path / "missing")


def test_rag_does_not_change_rules_evaluation() -> None:
    scheme = load_scheme(PROJECT_ROOT / "backend/app/rules/schemes/pm_kisan_mock.yaml")
    decision = evaluate(
        scheme,
        {
            "land_owned_hectares": 2.0,
            "holder_type": "individual",
            "is_income_tax_payer": False,
        },
    )
    assert decision.outcome is DecisionOutcome.ELIGIBLE


def test_graph_plan_and_explain_use_rag_without_deciding_eligibility(tmp_path: Path) -> None:
    retriever = ingest_rulebooks(
        RULEBOOKS,
        tmp_path / "index",
        use_chroma=False,
        force_fallback=True,
    )
    state = CaseState(
        case_id=str(uuid4()),
        language="en",
        channel="web",
        transcript_en="I need an education scholarship as a student",
        status="NOT_ELIGIBLE",
    )
    plan(state, SimpleNamespace(retriever=retriever))
    assert state.candidate_schemes[0] == "state_scholarship_mock"

    notifier = FakeNotifier()
    runtime = GraphDependencies(
        session=None,
        speech=None,
        classifier=None,
        ocr=None,
        llm=FakeLLMClient(),
        retriever=retriever,
        portal=None,
        notifier=notifier,
    )
    explain(state, runtime)
    assert "state_scholarship_mock.md" in notifier.messages[-1]["text"]
