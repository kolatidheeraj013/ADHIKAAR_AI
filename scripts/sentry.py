"""Adhikaar Sentry: Lightweight background auto-wake sentinel for Telegram.

Option A: 100% Local, Zero Cloud Setup.
Monitors incoming Telegram messages when the main Adhikaar AI services
are offline. When a citizen interacts with @Adhikaar013bot:
1. Sends an immediate warm acknowledgement to the citizen.
2. Optionally alerts the administrator (ADMIN_TELEGRAM_CHAT_ID).
3. Automatically launches `scripts/start_all.ps1` to spin up Backend, Mock Portal,
   and Telegram Bot.
4. Yields polling to the main bot service once port 8200 becomes healthy.
5. Resumes standby watching if the main services are stopped later.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SENTRY] %(message)s",
)
logger = logging.getLogger("adhikaar_sentry")

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env_vars() -> dict[str, str]:
    """Load configuration from .env.local and .env files."""
    env_vars: dict[str, str] = {}
    for filename in (".env.local", ".env"):
        env_path = REPO_ROOT / filename
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            except Exception as exc:
                logger.debug("Could not read %s: %s", filename, exc)
    return env_vars


def is_service_healthy(url: str, timeout: float = 1.0) -> bool:
    """Check if a service /health endpoint responds with 200 OK."""
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def send_telegram_message(
    token: str,
    chat_id: int | str,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> bool:
    """Deliver a simple text message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        resp = httpx.post(url, json=payload, timeout=10.0)
        return resp.status_code == 200
    except Exception as exc:
        logger.warning("Failed to send Telegram message to %s: %s", chat_id, exc)
        return False


def trigger_start_all() -> bool:
    """Execute scripts/start_all.ps1 in a non-blocking subprocess."""
    start_script = REPO_ROOT / "scripts" / "start_all.ps1"
    if not start_script.is_file():
        logger.error("start_all.ps1 not found at %s", start_script)
        return False

    logger.info("⚡ Automatically triggering %s ...", start_script)
    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(start_script),
            ],
            cwd=str(REPO_ROOT),
        )
        return True
    except Exception as exc:
        logger.error("Failed to execute start_all.ps1: %s", exc)
        return False


def run_sentry(poll_timeout: int = 15) -> None:
    """Run the main Sentry loop."""
    config = load_env_vars()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "dummy-token-for-tests-only":
        logger.error(
            "TELEGRAM_BOT_TOKEN not configured in .env.local or environment. "
            "Please configure the token first."
        )
        sys.exit(1)

    admin_chat_id = (
        os.environ.get("ADMIN_TELEGRAM_CHAT_ID")
        or config.get("ADMIN_TELEGRAM_CHAT_ID")
        or os.environ.get("ADMIN_CHAT_ID")
        or config.get("ADMIN_CHAT_ID")
    )
    bot_health_url = "http://127.0.0.1:8200/health"

    logger.info("🛡️ Adhikaar Sentry started. Listening for citizen engagement...")
    if admin_chat_id:
        logger.info("Admin alerts enabled for Telegram Chat ID: %s", admin_chat_id)

    offset: int | None = None

    while True:
        try:
            # If main bot is already running and healthy, enter passive monitoring
            if is_service_healthy(bot_health_url, timeout=1.5):
                logger.debug("Main bot service active on 8200. Sentry sleeping...")
                time.sleep(5.0)
                continue

            # Main bot is offline -> Sentry actively polls Telegram for citizen wakeup
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params: dict[str, int] = {"timeout": poll_timeout, "limit": 10}
            if offset is not None:
                params["offset"] = offset

            try:
                resp = httpx.get(url, params=params, timeout=poll_timeout + 5)
            except httpx.TimeoutException:
                continue
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409:
                    time.sleep(4.0)
                    continue
                logger.warning("Telegram API HTTP error: %s", exc)
                time.sleep(5.0)
                continue
            except Exception as exc:
                logger.warning("Telegram connection error: %s", exc)
                time.sleep(3.0)
                continue

            if resp.status_code != 200:
                time.sleep(3.0)
                continue

            data = resp.json()
            updates = data.get("result", [])
            if not updates:
                continue

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("callback_query", {}).get("message")
                if not msg:
                    continue

                chat = msg.get("chat", {})
                chat_id = chat.get("id")
                from_user = msg.get("from", {})
                username = from_user.get("username") or from_user.get("first_name") or "Citizen"

                if not chat_id:
                    continue

                logger.info("Citizen %s (%s) engaged bot while offline!", username, chat_id)

                # 1. Warm citizen acknowledgement
                send_telegram_message(
                    token,
                    chat_id,
                    "🙏 Namaste! Adhikaar AI services are securely initializing on our server.\n\n"
                    "Please wait about 15-20 seconds. Your session will start automatically!",
                )

                # 2. Alert administrator if configured
                if admin_chat_id:
                    send_telegram_message(
                        token,
                        admin_chat_id,
                        f"🚨 Adhikaar Sentry Alert\n"
                        f"Citizen @{username} (ID: {chat_id}) just opened @Adhikaar013bot!\n"
                        f"Automatically launching all services via start_all.ps1...",
                    )

                # 3. Automatically trigger start_all.ps1
                trigger_start_all()

                # 4. Wait for up to 45 seconds for main bot to report healthy
                logger.info("Waiting for services to become healthy on port 8200...")
                started_time = time.time()
                is_ready = False
                while time.time() - started_time < 45.0:
                    time.sleep(3.0)
                    if is_service_healthy(bot_health_url, timeout=1.5):
                        is_ready = True
                        break

                if is_ready:
                    logger.info("✅ Services up! Sending ready confirmation to %s...", chat_id)
                    send_telegram_message(
                        token,
                        chat_id,
                        "✅ Adhikaar AI services are now ready!\n\n"
                        "Send your message, document photo, or tap Start below to proceed:",
                        reply_markup={
                            "inline_keyboard": [
                                [
                                    {
                                        "text": "🚀 Start Application",
                                        "callback_data": "start:new",
                                    }
                                ]
                            ]
                        },
                    )
                else:
                    logger.warning("Services took >45s to spin up. Standby loop will retry.")

                break

        except KeyboardInterrupt:
            logger.info("Sentry stopped by user.")
            break
        except Exception as exc:
            logger.exception("Unexpected error in Sentry loop: %s", exc)
            time.sleep(5.0)


if __name__ == "__main__":
    run_sentry()
