from fastapi.testclient import TestClient

from app.main import app


def test_telegram_bot_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "telegram_bot", "status": "ok"}


def test_telegram_bot_readiness_is_not_green_without_a_running_application() -> None:
    previous_application = app.state.telegram_application
    previous_ready = app.state.telegram_ready
    app.state.telegram_application = None
    app.state.telegram_ready = False
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.state.telegram_application = previous_application
        app.state.telegram_ready = previous_ready

    assert response.status_code == 503


def test_telegram_webhook_requires_secret_before_application_dispatch() -> None:
    app.state.telegram_webhook_secret = "test-webhook-secret"
    app.state.telegram_application = None
    client = TestClient(app)
    try:
        unauthorized = client.post("/telegram/webhook", json={})
        assert unauthorized.status_code == 401

        unavailable = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"},
            json={},
        )
        assert unavailable.status_code == 503
    finally:
        app.state.telegram_webhook_secret = ""


def test_internal_notify_renders_notification_keyboard() -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    fake_bot = FakeBot()
    app.state.service_token = "test-service-token"
    app.state.telegram_application = type(
        "FakeTelegramApplication",
        (),
        {
            "bot": fake_bot,
            "bot_data": {},
        },
    )()
    try:
        response = TestClient(app).post(
            "/internal/notify",
            headers={"X-Service-Token": "test-service-token"},
            json={
                "chat_id": 42,
                "case_id": "case-1",
                "message_id": "message-1",
                "text": "Choose one",
                "options": [{"label": "Yes", "value": True}],
            },
        )
    finally:
        app.state.telegram_application = None
        app.state.service_token = ""

    assert response.status_code == 200
    assert fake_bot.sent[0]["chat_id"] == 42
    assert fake_bot.sent[0]["reply_markup"].inline_keyboard[0][0].callback_data.startswith("a:")
