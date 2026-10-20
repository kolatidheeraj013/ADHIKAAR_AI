from __future__ import annotations

import asyncio

import app.main as portal_module
import pytest
from app.main import ApplicationRequest, app, submit_application
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_portal_state() -> None:
    portal_module._fail_mode = "none"
    portal_module._applications.clear()
    portal_module._next_reference = 1


def test_application_validation_and_deterministic_status() -> None:
    client = TestClient(app)
    missing = client.post(
        "/applications",
        json={"scheme_id": "pm_kisan_mock", "payload_fields": {"applicant_name": "Sample"}},
    )
    assert missing.status_code == 422
    assert {item["field"] for item in missing.json()["errors"]} == {
        "aadhaar_last4",
        "bank_account_number",
        "bank_ifsc",
    }

    payload = {
        "applicant_name": "Sample Farmer",
        "aadhaar_last4": "9012",
        "bank_account_number": "SYNTHETIC-ACCOUNT",
        "bank_ifsc": "SYNTHETICIFSC",
    }
    created = client.post(
        "/applications", json={"scheme_id": "pm_kisan_mock", "payload_fields": payload}
    )
    assert created.status_code == 200
    assert created.json() == {"portal_ref": "MOCK-PORTAL-0001"}
    assert client.get("/applications/MOCK-PORTAL-0001").json() == {
        "portal_ref": "MOCK-PORTAL-0001",
        "status": "accepted",
    }


@pytest.mark.parametrize("fail_mode", ["none", "timeout", "reject_permanent"])
def test_dev_config_accepts_supported_failure_modes(fail_mode: str) -> None:
    response = TestClient(app).post("/dev/config", json={"fail_mode": fail_mode})
    assert response.status_code == 200
    assert response.json() == {"fail_mode": fail_mode}


def test_timeout_mode_hangs_until_cancelled() -> None:
    portal_module._fail_mode = "timeout"
    request = ApplicationRequest(
        scheme_id="pm_kisan_mock", payload_fields={"applicant_name": "Sample"}
    )
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(submit_application(request), timeout=0.01))


def test_permanent_mode_returns_non_fixable_error() -> None:
    client = TestClient(app)
    assert client.post("/dev/config", json={"fail_mode": "reject_permanent"}).status_code == 200
    response = client.post(
        "/applications",
        json={"scheme_id": "pm_kisan_mock", "payload_fields": {}},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "duplicate_application"
