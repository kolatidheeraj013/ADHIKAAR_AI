from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
from app.core.config import Settings
from app.db.models import Case
from app.integrations.notifier import NoopNotifier, TelegramNotifier
from app.main import _ServiceState


def test_telegram_notifier_posts_internal_payload_and_service_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    notifier = TelegramNotifier(
        bot_internal_url="http://bot.test/",
        service_token="service-test",
        chat_id="12345",
        transport=httpx.MockTransport(handler),
    )

    delivered = asyncio.run(
        notifier.notify_async(
            case_id="case-1",
            language="ta",
            kind="question",
            text="Does anyone in your family pay income tax?",
            options=[{"label": "Yes", "value": True}, {"label": "No", "value": False}],
            message_id="message-1",
        )
    )

    assert delivered is True
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "http://bot.test/internal/notify"
    assert request.headers["X-Service-Token"] == "service-test"
    assert json.loads(request.content) == {
        "chat_id": "12345",
        "case_id": "case-1",
        "kind": "question",
        "language": "ta",
        "text": "Does anyone in your family pay income tax?",
        "options": [
            {"label": "Yes", "idx": True},
            {"label": "No", "idx": False},
        ],
        "message_id": "message-1",
    }


def test_telegram_notifier_reports_bounded_failures_without_raising() -> None:
    failures: list[tuple[Any, ...]] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    notifier = TelegramNotifier(
        bot_internal_url="http://bot.test",
        service_token="service-test",
        chat_id="12345",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
        on_delivery=lambda *result: failures.append(result),
    )

    delivered = asyncio.run(
        notifier.notify_async(
            case_id="case-1",
            language="en",
            kind="result",
            text="done",
            message_id="message-1",
        )
    )

    assert delivered is False
    assert len(notifier.failures) == 1
    assert notifier.failures[0]["message_id"] == "message-1"
    assert failures == [("message-1", "case-1", "result", False, 2, "HTTPStatusError")]


def test_offline_mode_uses_telegram_notifier_only_for_telegram_cases(tmp_path) -> None:
    service = _ServiceState(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'notifier.db'}",
            storage_dir=tmp_path / "storage",
            demo_mode="offline",
            service_token="service-secret",
            bot_internal_url="http://bot.test",
        )
    )
    telegram_case = Case(id=uuid4(), language="en", channel="telegram", channel_ref="chat-123")
    web_case = Case(id=uuid4(), language="en", channel="web", channel_ref="web-session")

    try:
        telegram_notifier = service._notifier_for_case(telegram_case)
        web_notifier = service._notifier_for_case(web_case)

        assert isinstance(telegram_notifier, TelegramNotifier)
        assert telegram_notifier.chat_id == "chat-123"
        assert web_notifier is service.notifier
        assert isinstance(web_notifier, NoopNotifier)
        assert service.settings.demo_mode == "offline"
        assert "service-secret" not in repr(telegram_notifier)
    finally:
        service.engine.dispose()


def test_telegram_payload_keeps_service_token_out_of_json() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    notifier = TelegramNotifier(
        bot_internal_url="http://bot.test",
        service_token="service-secret",
        chat_id="chat-123",
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(
        notifier.notify_async(
            case_id="case-1",
            language="en",
            kind="result",
            text="Synthetic result",
            message_id="message-1",
        )
    )

    payload = json.loads(requests[0].content)
    assert "service-secret" not in requests[0].content.decode()
    assert "service_token" not in payload
