"""FastAPI lifecycle and HTTP ingress for the real Telegram application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from hmac import compare_digest
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from telegram import Update

try:
    from dotenv import load_dotenv

    _root_dir = Path(__file__).resolve().parents[2]
    if (_root_dir / ".env.local").is_file():
        load_dotenv(_root_dir / ".env.local", override=False)
    if (_root_dir / ".env").is_file():
        load_dotenv(_root_dir / ".env", override=False)
except Exception:
    pass

from .bot import build_application, handle_notification


def _mode() -> str:
    return os.getenv("TELEGRAM_MODE", "polling").strip().lower()


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Run PTB alongside FastAPI without taking over uvicorn's event loop."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        # Health and offline API tests deliberately run without Telegram credentials.
        yield
        return

    telegram_application = build_application(token)
    application.state.telegram_application = telegram_application
    initialized = False
    started = False
    polling = False
    try:
        await telegram_application.initialize()
        initialized = True

        mode = _mode()
        if mode == "polling":
            await telegram_application.updater.start_polling(drop_pending_updates=True)
            polling = True
            await telegram_application.start()
            started = True
        elif mode == "webhook":
            secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
            webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
            if not secret or not webhook_url:
                raise RuntimeError(
                    "TELEGRAM_WEBHOOK_SECRET and TELEGRAM_WEBHOOK_URL are required in webhook mode"
                )
            application.state.telegram_webhook_secret = secret
            await telegram_application.bot.set_webhook(
                webhook_url, secret_token=secret, drop_pending_updates=True
            )
            await telegram_application.start()
            started = True
        else:
            raise RuntimeError("TELEGRAM_MODE must be 'polling' or 'webhook'")
        yield
    finally:
        if polling and telegram_application.updater:
            await telegram_application.updater.stop()
        if started:
            await telegram_application.stop()
        if initialized:
            await telegram_application.shutdown()
        application.state.telegram_application = None


app = FastAPI(title="ADHIKAAR Telegram Bot", version="0.1.0", lifespan=lifespan)
app.state.telegram_application = None
app.state.telegram_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
app.state.service_token = os.getenv("SERVICE_TOKEN", "")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a stable liveness response for local orchestration."""
    return {"service": "telegram_bot", "status": "ok"}


@app.post("/internal/notify", tags=["internal"])
async def internal_notify(
    payload: dict[str, Any], x_service_token: str | None = Header(default=None)
) -> dict[str, bool]:
    """Receive a localized backend notification and deliver it to Telegram."""
    expected = str(app.state.service_token or "")
    if expected and not compare_digest(x_service_token or "", expected):
        raise HTTPException(status_code=401, detail="invalid service token")
    application = app.state.telegram_application
    if application is None:
        raise HTTPException(status_code=503, detail="telegram application is not running")
    await handle_notification(payload, application)
    return {"ok": True}


@app.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(
    payload: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Accept Telegram webhook updates after validating Telegram's secret header."""
    expected = str(app.state.telegram_webhook_secret or "")
    supplied = x_telegram_bot_api_secret_token or ""
    if not expected or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid telegram webhook secret")
    application = app.state.telegram_application
    if application is None:
        raise HTTPException(status_code=503, detail="telegram application is not running")
    update = Update.de_json(payload, application.bot)
    if update is None:
        raise HTTPException(status_code=400, detail="invalid telegram update")
    await application.process_update(update)
    return {"ok": True}
