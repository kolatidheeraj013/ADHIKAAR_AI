"""Notifier implementations used by backend graph nodes."""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx

DeliveryCallback = Callable[[str, str, str, bool, int, str | None], None]


@dataclass(frozen=True)
class _Notification:
    case_id: str
    chat_id: str
    language: str
    kind: str
    text: str
    options: list[dict[str, Any]]
    message_id: str


def _telegram_options(options: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Use the compact callback contract expected by the Telegram service."""
    result: list[dict[str, Any]] = []
    for index, option in enumerate(options or []):
        result.append(
            {
                "label": str(option.get("label", option.get("option", ""))),
                "idx": option.get("idx", option.get("value", index)),
            }
        )
    return result


@dataclass
class NoopNotifier:
    """Record notifications without calling a network service.

    The web client reads persisted messages and SSE events, so a local run does
    not need Telegram or another push transport. Keeping the messages here is
    useful for tests and preserves the notifier boundary used by the graph.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)

    def notify(
        self,
        case_id: str,
        language: str,
        kind: str,
        text: str,
        options: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> bool:
        self.messages.append(
            {
                "case_id": case_id,
                "language": language,
                "kind": kind,
                "text": text,
                "options": options or [],
            }
        )
        return True


@dataclass
class TelegramNotifier:
    """Deliver backend notifications to the bot without blocking graph nodes.

    ``notify`` only performs a bounded, non-blocking queue operation. The
    worker runs the real async HTTP implementation and reports the final
    result through ``on_delivery``. The backend never receives or stores the
    Telegram Bot API token; authentication here is only the shared internal
    service token.
    """

    bot_internal_url: str
    service_token: str = field(repr=False)
    chat_id: str
    timeout_seconds: float = 3.0
    max_attempts: int = 3
    queue_size: int = 32
    on_delivery: DeliveryCallback | None = None
    transport: httpx.AsyncBaseTransport | None = None
    failures: list[dict[str, Any]] = field(default_factory=list, init=False)
    _queue: queue.Queue[_Notification | None] = field(init=False, repr=False)
    _worker: threading.Thread = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue = queue.Queue(maxsize=max(1, self.queue_size))
        self._worker = threading.Thread(
            target=self._run_worker,
            name="telegram-notifier",
            daemon=True,
        )
        self._worker.start()

    @property
    def endpoint(self) -> str:
        return f"{self.bot_internal_url.rstrip('/')}/internal/notify"

    def notify(
        self,
        case_id: str,
        language: str,
        kind: str,
        text: str,
        options: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> None:
        notification = _Notification(
            case_id=case_id,
            chat_id=self.chat_id,
            language=language,
            kind=kind,
            text=text,
            options=_telegram_options(options),
            message_id=message_id or str(uuid4()),
        )
        try:
            self._queue.put_nowait(notification)
        except queue.Full:
            self._record_failure(notification, 0, "delivery queue is full", defer_callback=True)
        return None

    async def notify_async(
        self,
        case_id: str,
        language: str,
        kind: str,
        text: str,
        options: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> bool:
        """Send one notification directly for async callers and tests."""
        notification = _Notification(
            case_id=case_id,
            chat_id=self.chat_id,
            language=language,
            kind=kind,
            text=text,
            options=_telegram_options(options),
            message_id=message_id or str(uuid4()),
        )
        return await self._deliver(notification)

    def _run_worker(self) -> None:
        while True:
            notification = self._queue.get()
            try:
                if notification is None:
                    return
                asyncio.run(self._deliver(notification))
            finally:
                self._queue.task_done()

    async def _deliver(self, notification: _Notification) -> bool:
        attempts = max(1, self.max_attempts)
        error: str | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.post(
                        self.endpoint,
                        headers={"X-Service-Token": self.service_token},
                        json={
                            "chat_id": notification.chat_id,
                            "case_id": notification.case_id,
                            "kind": notification.kind,
                            "language": notification.language,
                            "text": notification.text,
                            "options": notification.options,
                            "message_id": notification.message_id,
                        },
                    )
                response.raise_for_status()
                if self.on_delivery:
                    self.on_delivery(
                        notification.message_id,
                        notification.case_id,
                        notification.kind,
                        True,
                        attempt,
                        None,
                    )
                return True
            except (httpx.HTTPError, OSError) as exc:
                error = type(exc).__name__
                if attempt < attempts:
                    await asyncio.sleep(0.05 * (2 ** (attempt - 1)))
        self._record_failure(notification, attempts, error or "delivery failed")
        return False

    def _record_failure(
        self,
        notification: _Notification,
        attempts: int,
        error: str,
        *,
        defer_callback: bool = False,
    ) -> None:
        evidence = {
            "message_id": notification.message_id,
            "kind": notification.kind,
            "attempts": attempts,
            "error_type": error,
        }
        self.failures.append(evidence)
        if self.on_delivery:
            callback_args = (
                notification.message_id,
                notification.case_id,
                notification.kind,
                False,
                attempts,
                error,
            )
            if defer_callback:
                threading.Thread(
                    target=self.on_delivery,
                    args=callback_args,
                    name="telegram-notifier-failure",
                    daemon=True,
                ).start()
            else:
                self.on_delivery(*callback_args)
