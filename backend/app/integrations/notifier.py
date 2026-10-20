"""Notifier implementations used by the web/offline Phase 8 flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    ) -> None:
        self.messages.append(
            {
                "case_id": case_id,
                "language": language,
                "kind": kind,
                "text": text,
                "options": options or [],
            }
        )
