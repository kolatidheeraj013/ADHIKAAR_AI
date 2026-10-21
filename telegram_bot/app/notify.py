"""Render backend notifications into Telegram-safe chunks and keyboards."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TELEGRAM_TEXT_LIMIT = 4096


def split_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split at a paragraph/word boundary while keeping every chunk within the limit."""
    if not text:
        return [""]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit + 1)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    chunks.append(remaining)
    return chunks


@dataclass(frozen=True)
class AnswerTarget:
    case_id: str
    message_id: str
    option: int | str


@dataclass(frozen=True)
class ActionTarget:
    """A short-lived bot UI action with no citizen or case data in Telegram."""

    action: str


class CallbackStore:
    """Opaque callback tokens keep case UUIDs and long values out of Telegram data."""

    def __init__(self) -> None:
        self._targets: dict[str, AnswerTarget] = {}
        self._actions: dict[str, ActionTarget] = {}

    def add(self, target: AnswerTarget, prefix: str = "a") -> str:
        token = f"{prefix}:{secrets.token_urlsafe(8)}"
        self._targets[token] = target
        if len(token.encode("utf-8")) > 64:
            raise ValueError("callback_data exceeds Telegram's 64-byte limit")
        return token

    def pop(self, token: str) -> AnswerTarget | None:
        return self._targets.pop(token, None)

    def get(self, token: str) -> AnswerTarget | None:
        return self._targets.get(token)

    def add_action(self, action: str, prefix: str = "u") -> str:
        token = f"{prefix}:{secrets.token_urlsafe(8)}"
        self._actions[token] = ActionTarget(action)
        if len(token.encode("utf-8")) > 64:
            raise ValueError("callback_data exceeds Telegram's 64-byte limit")
        return token

    def pop_action(self, token: str) -> ActionTarget | None:
        return self._actions.pop(token, None)

    def get_action(self, token: str) -> ActionTarget | None:
        return self._actions.get(token)


def question_keyboard(
    options: list[dict[str, Any]], *, case_id: str, message_id: str, callbacks: CallbackStore
) -> InlineKeyboardMarkup:
    buttons = []
    for option in options:
        label = str(option.get("label", option.get("option", "")))
        idx = option.get("idx", option.get("value", label))
        token = callbacks.add(AnswerTarget(case_id, str(message_id), idx))
        buttons.append([InlineKeyboardButton(label, callback_data=token)])
    return InlineKeyboardMarkup(buttons)


def render_notification(
    payload: dict[str, Any], *, callbacks: CallbackStore | None = None
) -> list[tuple[str, InlineKeyboardMarkup | None]]:
    """Return Telegram-safe text chunks paired with an optional question keyboard."""
    callbacks = callbacks or CallbackStore()
    keyboard = None
    options = payload.get("options") or []
    if options:
        keyboard = question_keyboard(
            options,
            case_id=str(payload.get("case_id", "")),
            message_id=str(payload.get("message_id", "")),
            callbacks=callbacks,
        )
    chunks = split_text(str(payload.get("text", "")))
    return [
        (chunk, keyboard if index == len(chunks) - 1 else None)
        for index, chunk in enumerate(chunks)
    ]
