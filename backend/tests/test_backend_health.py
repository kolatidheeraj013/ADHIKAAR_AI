from __future__ import annotations

from uuid import uuid4

from app.db.models import Application, Case, Escalation
from app.db.session import build_session_factory
from app.integrations.fakes import FakePortalClient
from app.main import _services, app
from fastapi.testclient import TestClient


def test_backend_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "backend"
    assert data["status"] == "ok"
    assert data["db"] == "healthy"
    assert data["checkpointer"] == "ready"


def test_backend_stats_and_metrics() -> None:
    client = TestClient(app)
    stats_res = client.get("/stats")
    metrics_res = client.get("/metrics")

    assert stats_res.status_code == 200
    assert metrics_res.status_code == 200
    data = stats_res.json()
    assert "total_cases" in data
    assert "by_status" in data
    assert "submitted_count" in data
    assert "escalated_count" in data
    assert "avg_node_latency_ms" in data


def test_track_case_normal_and_stalled() -> None:
    client = TestClient(app)
    session = _services().sessions()

    # Create test case and application
    case_id = uuid4()
    case = Case(id=case_id, language="ta", channel="web", status="COMPLETED")
    app_rec = Application(
        case_id=case_id,
        scheme_id="pm_kisan_mock",
        payload={"applicant_name": "Murugan K"},
        portal_ref="MOCK-PORTAL-8888",
        status="SUBMITTED",
        attempts=1,
    )
    session.add(case)
    session.add(app_rec)
    session.commit()
    session.close()

    # 1. Normal status poll
    res = client.post(f"/cases/{case_id}/track")
    assert res.status_code == 200
    data = res.json()
    assert data["portal_status"] == "accepted"
    assert data["sla_escalated"] is False

    # 2. Simulate stalled portal status
    original_factory = _services().runtime_factory

    def stalled_factory(s, cid):
        runtime = original_factory(s, cid)
        runtime.portal = FakePortalClient(fail_mode="stalled")
        return runtime

    _services().runtime_factory = stalled_factory
    try:
        res_stalled = client.post(f"/cases/{case_id}/track")
        assert res_stalled.status_code == 200
        stalled_data = res_stalled.json()
        assert stalled_data["portal_status"] == "stalled"
        assert stalled_data["sla_escalated"] is True

        # Check DB escalation created
        verify_session = _services().sessions()
        esc = verify_session.query(Escalation).filter_by(case_id=case_id).first()
        assert esc is not None
        assert esc.reason == "portal_sla_stalled"
        assert esc.status == "OPEN"
        verify_session.close()
    finally:
        _services().runtime_factory = original_factory
