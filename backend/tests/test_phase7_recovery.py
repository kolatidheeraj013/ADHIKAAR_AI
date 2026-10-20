from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.agents.graph import build_graph, run_case
from app.db.models import Case
from app.db.session import build_engine, build_session_factory, init_db
from app.integrations.fakes import FakePortalClient
from langgraph.checkpoint.memory import InMemorySaver
from test_phase3_graph import _documents, _runtime, _state


@pytest.fixture
def graph_context(tmp_path: Path):
    engine = build_engine(f"sqlite:///{tmp_path / 'graph.db'}")
    init_db(engine)
    session = build_session_factory(engine)()
    case_id = uuid4()
    session.add(Case(id=case_id, language="ta", channel="web", status="RECEIVED"))
    session.commit()
    yield session, str(case_id)
    session.close()
    engine.dispose()


class FiveHundredPortal(FakePortalClient):
    def submit(self, scheme_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.submit_calls += 1
        self.submissions.append({"scheme_id": scheme_id, "payload": dict(payload)})
        return {
            "ok": False,
            "error": {
                "kind": "transient",
                "code": "http_503",
                "message": "temporary server error",
            },
        }


def test_http_5xx_retries_twice_and_escalates_with_evidence(graph_context) -> None:
    session, case_id = graph_context
    portal = FiveHundredPortal()
    runtime = _runtime(session, portal=portal)
    graph = build_graph(runtime, checkpointer=InMemorySaver())

    result = run_case(graph, _state(case_id, _documents()), thread_id=case_id)

    assert result.interrupts
    assert result.state.status == "NEEDS_REVIEW"
    assert portal.submit_calls == 3
    assert result.state.escalation is not None
    evidence = result.state.escalation.evidence
    assert evidence["document_ids"] == ["aadhaar.png", "bank_passbook.png", "land_record.png"]
    assert "rule_trace" in evidence
    assert evidence["portal_error"]["code"] == "http_503"
    assert evidence["tried"]["submit:pm_kisan_mock"] == 2
