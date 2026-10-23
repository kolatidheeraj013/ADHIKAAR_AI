from __future__ import annotations

import io
import sys
import wave
from pathlib import Path
from uuid import UUID

BACKEND_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]

import pytest  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.db.models import Case  # noqa: E402
from app.main import _ServiceState, app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path: Path):
    configured = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        storage_dir=tmp_path / "storage",
        service_token="service-test",
        reviewer_password="reviewer-test",
        max_upload_mb=1,
    )
    app.state.services = _ServiceState(configured)
    with TestClient(app) as test_client:
        yield test_client
    app.state.services.engine.dispose()


def _create(
    client: TestClient,
    text: str = "farmer PM-Kisan nobody pays tax",
    *,
    channel: str = "web",
    channel_ref: str | None = None,
) -> str:
    payload = {"language": "en", "consent": True, "channel": channel}
    if channel_ref is not None:
        payload["channel_ref"] = channel_ref
    case_id = client.post("/cases", json=payload).json()["case_id"]
    assert client.post(f"/cases/{case_id}/text", json={"text": text}).status_code == 200
    sample = b"\x89PNG\r\n\x1a\nSAMPLE"
    for name in ("aadhaar.png", "land_record.png", "bank_passbook.png"):
        assert (
            client.post(
                f"/cases/{case_id}/documents", files={"file": (name, sample, "image/png")}
            ).status_code
            == 200
        )
    return case_id


def test_case_flow_is_idempotent_and_citizen_safe(client: TestClient) -> None:
    case_id = _create(client)
    first = client.post(f"/cases/{case_id}/start")
    second = client.post(f"/cases/{case_id}/start")
    assert first.status_code == second.status_code == 200
    assert second.json()["idempotent"] is True
    view = client.get(f"/cases/{case_id}").json()
    assert view["status"] == "COMPLETED"
    assert "facts" not in view and "evidence" not in view
    assert all("SYNTHETIC-ACCOUNT" not in message["text"] for message in view["messages"])
    events = client.get(f"/cases/{case_id}/events")
    assert events.status_code == 200
    assert "raw_text" not in events.text


def test_upload_requires_consent_and_magic_bytes(client: TestClient) -> None:
    case_id = client.post("/cases", json={"language": "en", "consent": True}).json()["case_id"]
    response = client.post(
        f"/cases/{case_id}/documents", files={"file": ("fake.png", b"not-an-image", "image/png")}
    )
    assert response.status_code == 415
    no_consent = client.post("/cases", json={"language": "en", "consent": False})
    assert no_consent.status_code == 422


def test_tokens_delete_and_reviewer_routes(client: TestClient) -> None:
    case_id = _create(client, "farmer PM-Kisan")
    assert (
        client.get("/cases/active", params={"channel": "web", "channel_ref": "none"}).status_code
        == 401
    )
    client.post(f"/cases/{case_id}/start")
    assert client.get("/reviewer/queue").status_code == 401
    deleted = client.delete(f"/cases/{case_id}")
    assert deleted.status_code == 200
    assert client.get(f"/cases/{case_id}").json()["messages"]


def test_question_resume_and_active_service_case(client: TestClient) -> None:
    case_id = _create(client, "farmer PM-Kisan")
    assert client.post(f"/cases/{case_id}/start").status_code == 200
    case = client.get(f"/cases/{case_id}").json()
    question = next(message for message in case["messages"] if message["kind"] == "question")
    answered = client.post(
        f"/cases/{case_id}/answers",
        json={"message_id": question["id"], "option": "No"},
    )
    assert answered.status_code == 200
    assert client.get(f"/cases/{case_id}").json()["status"] == "COMPLETED"

    active_case_id = client.post(
        "/cases",
        json={"language": "en", "consent": True, "channel": "telegram", "channel_ref": "chat-1"},
    ).json()["case_id"]
    active = client.get(
        "/cases/active",
        params={"channel": "telegram", "channel_ref": "chat-1"},
        headers={"X-Service-Token": "service-test"},
    )
    assert active.status_code == 200
    assert active.json()["case"]["case_id"] == active_case_id


def test_latest_service_case_includes_terminal_result(client: TestClient) -> None:
    case_id = _create(client, "farmer PM-Kisan", channel="telegram", channel_ref="chat-latest")
    assert client.post(f"/cases/{case_id}/start").status_code == 200
    question = next(
        message
        for message in client.get(f"/cases/{case_id}").json()["messages"]
        if message["kind"] == "question"
    )
    assert (
        client.post(
            f"/cases/{case_id}/answers",
            json={"message_id": question["id"], "option": "No"},
        ).status_code
        == 200
    )
    latest = client.get(
        "/cases/latest",
        params={"channel": "telegram", "channel_ref": "chat-latest"},
        headers={"X-Service-Token": "service-test"},
    )
    assert latest.status_code == 200
    assert latest.json()["case"]["case_id"] == case_id
    assert latest.json()["case"]["status"] == "COMPLETED"


def test_reviewer_can_resume_blurry_case(client: TestClient) -> None:
    # A fresh case keeps the blurry-document scenario independent of the helper.
    case_id = client.post("/cases", json={"language": "en", "consent": True}).json()["case_id"]
    assert (
        client.post(
            f"/cases/{case_id}/text", json={"text": "farmer PM-Kisan nobody pays tax"}
        ).status_code
        == 200
    )
    sample = b"\x89PNG\r\n\x1a\nSAMPLE"
    for name in ("aadhaar.png", "land_record_blurry.png", "bank_passbook.png"):
        assert (
            client.post(
                f"/cases/{case_id}/documents", files={"file": (name, sample, "image/png")}
            ).status_code
            == 200
        )
    client.post(f"/cases/{case_id}/start")
    assert client.get(f"/cases/{case_id}").json()["status"] == "NEEDS_REVIEW"
    queue = client.get("/reviewer/queue", headers={"X-Reviewer-Token": "reviewer-test"})
    assert any(item["case_id"] == case_id for item in queue.json())
    resumed = client.post(
        f"/reviewer/{case_id}/resume",
        headers={"X-Reviewer-Token": "reviewer-test"},
        json={"action": "approve", "note": "synthetic demo review"},
    )
    assert resumed.status_code == 200
    assert client.get(f"/cases/{case_id}").json()["status"] == "COMPLETED"


def test_voice_validation_and_blank_text(client: TestClient) -> None:
    case_id = client.post("/cases", json={"language": "en", "consent": True}).json()["case_id"]

    blank = client.post(f"/cases/{case_id}/text", json={"text": "   "})
    assert blank.status_code == 422

    invalid_voice = client.post(
        f"/cases/{case_id}/voice",
        files={"file": ("voice.ogg", b"not-audio", "audio/ogg")},
    )
    assert invalid_voice.status_code == 415

    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)
    accepted = client.post(
        f"/cases/{case_id}/voice",
        files={"file": ("voice.wav", audio.getvalue(), "audio/wav")},
    )
    assert accepted.status_code == 200
    session = app.state.services.sessions()
    try:
        assert session.get(Case, UUID(case_id)).voice_storage_path
    finally:
        session.close()


def test_missing_document_reentry_and_reviewer_evidence(client: TestClient) -> None:
    case_id = client.post("/cases", json={"language": "en", "consent": True}).json()["case_id"]
    assert (
        client.post(
            f"/cases/{case_id}/text", json={"text": "farmer PM-Kisan nobody pays tax"}
        ).status_code
        == 200
    )
    sample = b"\x89PNG\r\n\x1a\nSAMPLE"
    for name in ("aadhaar.png", "bank_passbook.png"):
        assert (
            client.post(
                f"/cases/{case_id}/documents", files={"file": (name, sample, "image/png")}
            ).status_code
            == 200
        )

    first = client.post(f"/cases/{case_id}/start")
    assert first.status_code == 200
    assert client.get(f"/cases/{case_id}").json()["status"] == "NEEDS_DOCUMENTS"

    assert (
        client.post(
            f"/cases/{case_id}/documents",
            files={"file": ("land_record.png", sample, "image/png")},
        ).status_code
        == 200
    )
    assert client.post(f"/cases/{case_id}/start").status_code == 200
    assert client.get(f"/cases/{case_id}").json()["status"] == "COMPLETED"

    blurry_id = client.post("/cases", json={"language": "en", "consent": True}).json()["case_id"]
    assert (
        client.post(
            f"/cases/{blurry_id}/text", json={"text": "farmer PM-Kisan nobody pays tax"}
        ).status_code
        == 200
    )
    for name in ("aadhaar.png", "land_record_blurry.png", "bank_passbook.png"):
        assert (
            client.post(
                f"/cases/{blurry_id}/documents", files={"file": (name, sample, "image/png")}
            ).status_code
            == 200
        )
    assert client.post(f"/cases/{blurry_id}/start").status_code == 200

    evidence = client.get(f"/reviewer/{blurry_id}", headers={"X-Reviewer-Token": "reviewer-test"})
    assert evidence.status_code == 200
    assert all(item["ocr_confidence"] == 0.95 for item in evidence.json()["documents"])
    assert "SYNTHETIC-ACCOUNT" not in evidence.text

    audit = client.get(
        f"/reviewer/{blurry_id}/audit", headers={"X-Reviewer-Token": "reviewer-test"}
    )
    assert audit.status_code == 200
    assert any(item["event_type"].startswith("node.") for item in audit.json())


def test_delete_purges_all_case_upload_metadata_but_keeps_audit(client: TestClient) -> None:
    case_id = _create(client)
    service = app.state.services
    assert any(path.startswith(f"{case_id}/") for path in service.upload_metadata)
    assert client.delete(f"/cases/{case_id}").status_code == 200
    assert not any(path.startswith(f"{case_id}/") for path in service.upload_metadata)
    case_storage = service.storage.root / case_id
    assert not case_storage.exists() or not any(case_storage.iterdir())
    audit = client.get(f"/reviewer/{case_id}/audit", headers={"X-Reviewer-Token": "reviewer-test"})
    assert audit.status_code == 200
    assert any(item["event_type"] == "case.deleted" for item in audit.json())
