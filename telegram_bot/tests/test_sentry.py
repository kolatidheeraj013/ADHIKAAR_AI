"""Unit tests for Adhikaar Sentry (Option A auto-wake sentinel)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.sentry import (  # noqa: E402
    is_service_healthy,
    load_env_vars,
    send_telegram_message,
    trigger_start_all,
)


def test_load_env_vars():
    """Verify env vars are loaded from config files."""
    env = load_env_vars()
    assert isinstance(env, dict)


def test_is_service_healthy_success():
    """Verify healthy check returns True on HTTP 200."""
    with patch("httpx.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        assert is_service_healthy("http://127.0.0.1:8200/health") is True


def test_is_service_healthy_failure():
    """Verify healthy check returns False on connection error or non-200."""
    with patch("httpx.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        assert is_service_healthy("http://127.0.0.1:8200/health") is False


def test_send_telegram_message_success():
    """Verify send_telegram_message makes expected POST request."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        ok = send_telegram_message("dummy-token", 123456, "Hello Citizen")
        assert ok is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["chat_id"] == 123456
        assert kwargs["json"]["text"] == "Hello Citizen"


def test_trigger_start_all():
    """Verify start_all.ps1 invocation triggers subprocess Popen."""
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        ok = trigger_start_all()
        assert ok is True
        mock_popen.assert_called_once()
