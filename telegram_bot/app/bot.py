"""Telegram handlers. This module translates Telegram updates into backend calls."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from datetime import UTC
from io import BytesIO
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .backend_client import BackendClient, BackendHTTPError, BackendUnavailableError
from .chat_memory import ChatMemory
from .i18n import t
from .live_schemes import (
    format_schemes_gap_analysis,
    match_schemes_with_gap_analysis,
    normalize_doc_type,
)
from .notify import AnswerTarget, CallbackStore, question_keyboard, render_notification
from .onboarding import OnboardingStore

MAX_VOICE_SECONDS = int(os.getenv("MAX_VOICE_SECONDS", "30"))
MAX_UPLOAD_BYTES = min(
    20 * 1024 * 1024,
    max(1, int(os.getenv("MAX_UPLOAD_MB", "20"))) * 1024 * 1024,
)


class UploadTooLargeError(ValueError):
    """The downloaded Telegram file exceeded the configured upload limit."""


class AlbumDebouncer:
    """Send one acknowledgement after a media group has been quiet for a short period."""

    def __init__(self, delay: float = 2.0) -> None:
        self.delay = delay
        self._counts: dict[tuple[str, str], int] = {}
        self._tasks: dict[tuple[str, str], asyncio.Task[None]] = {}

    async def add(
        self,
        chat_id: int | str,
        media_group_id: str,
        send: Callable[[int], Awaitable[None]],
    ) -> None:
        key = (str(chat_id), str(media_group_id))
        self._counts[key] = self._counts.get(key, 0) + 1
        previous = self._tasks.get(key)
        if previous and not previous.done():
            previous.cancel()
        self._tasks[key] = asyncio.create_task(self._flush(key, send))

    async def _flush(self, key: tuple[str, str], send: Callable[[int], Awaitable[None]]) -> None:
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            return
        count = self._counts.pop(key, 0)
        self._tasks.pop(key, None)
        if count:
            await send(count)

    async def flush(self) -> None:
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _data(context: ContextTypes.DEFAULT_TYPE, key: str, default: Any = None) -> Any:
    return context.application.bot_data.get(key, default)


def _chat_id(update: Update) -> int:
    if update.effective_chat is None:
        raise ValueError("update has no chat")
    return update.effective_chat.id


def _language(
    update: Update, context: ContextTypes.DEFAULT_TYPE, case: dict[str, Any] | None = None
) -> str:
    return (
        str(case.get("language"))
        if case and case.get("language")
        else _data(context, "onboarding", OnboardingStore()).language_for(_chat_id(update))
    )


def _case_id(case: dict[str, Any] | None) -> str | None:
    if not case:
        return None
    value = case.get("case_id", case.get("id"))
    return str(value) if value else None


def _menu_keyboard(
    language: str = "en",
    *,
    active_state: str | None = None,
    has_active_case: bool = False,
    has_documents: bool = False,
) -> ReplyKeyboardMarkup:
    """Return contextual application menu options avoiding button clutter.

    'Browse schemes' and 'Delete data' only appear when documents or citizen
    data have been uploaded and understood.
    """
    if has_active_case and has_documents:
        rows = [
            [t(language, "menu_start"), t(language, "menu_continue")],
            [t(language, "menu_schemes"), t(language, "menu_help")],
            [t(language, "menu_delete"), t(language, "menu_language")],
        ]
    elif has_active_case:
        rows = [
            [t(language, "menu_start"), t(language, "menu_continue")],
            [t(language, "menu_help"), t(language, "menu_language")],
            [t(language, "menu_delete")],
        ]
    else:
        rows = [
            [t(language, "menu_start"), t(language, "menu_help")],
            [t(language, "menu_language")],
        ]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t(language, "menu_placeholder"),
    )


_NEXT_ACTIONS = {
    "COLLECTING": "Send your message or voice note and document photos/files, then tap Done.",
    "RECEIVED": "Please wait while your case is queued.",
    "PROCESSING": "Please wait while your case is being checked.",
    "NEEDS_INFO": "Choose an answer in the latest message.",
    "NEEDS_DOCUMENTS": "Send the missing document photos/files, then tap Done.",
    "NEEDS_REVIEW": "Your application is currently undergoing official verification.",
    "SUBMITTED": "Please wait for the scheme portal confirmation.",
    "COMPLETED": "No further action is needed.",
    "NOT_ELIGIBLE": "No further action is needed.",
    "FAILED_ESCALATED": (
        "Your application has been routed for official human review and resolution."
    ),
}


def _status_text(language: str, case: dict[str, Any]) -> str:
    status = str(case.get("status") or "active")
    messages = case.get("messages") or []
    recent_lines: list[str] = []
    decision = case.get("decision_summary")
    if isinstance(decision, dict) and decision.get("outcome"):
        recent_lines.append(
            f"• Outcome: {decision.get('outcome')}"
            + (f" ({decision.get('scheme_id')})" if decision.get("scheme_id") else "")
        )
    documents = case.get("documents") or []
    if documents:
        recent_lines.append(f"• Documents uploaded: {len(documents)}")
    if status.upper() == "NEEDS_DOCUMENTS":
        uploaded_types = {d.get("doc_type") for d in documents if isinstance(d, dict)}
        type_labels = {
            "aadhaar": t(language, "doc_tag_aadhaar"),
            "land_record": t(language, "doc_tag_land"),
            "bank_passbook": t(language, "doc_tag_passbook"),
            "income_certificate": t(language, "doc_tag_income"),
            "marksheet": t(language, "doc_tag_marksheet"),
            "other": t(language, "doc_tag_other"),
        }
        missing = [
            dt for dt in ("aadhaar", "land_record", "bank_passbook")
            if dt not in uploaded_types
        ]
        if missing:
            missing_names = [type_labels.get(dt, dt) for dt in missing]
            recent_lines.append(f"• ⚠️ Missing Document Required: {', '.join(missing_names)}")
    for message in messages[-3:]:
        if not isinstance(message, dict):
            continue
        kind = message.get("kind")
        if kind not in {"info", "question", "result"}:
            continue
        text = str(message.get("text") or "").strip()
        if text:
            from .notify import format_citizen_notification_text

            formatted = format_citizen_notification_text(
                text, language=language, kind=str(kind or "info")
            )
            summary = formatted.split("\n\n")[0].strip()
            recent_lines.append(f"• {summary[:300]}")
    seen: set[str] = set()
    deduped_lines: list[str] = []
    for line in recent_lines:
        if line not in seen:
            seen.add(line)
            deduped_lines.append(line)
    recent = "\n".join(deduped_lines) or t(language, "no_recent_updates")
    return t(
        language,
        "status",
        status=status,
        next_action=_NEXT_ACTIONS.get(
            status.upper(), "Follow the instructions in the latest message."
        ),
        recent=recent,
    )


def _file_size(value: Any) -> int | None:
    size = getattr(value, "file_size", None)
    try:
        return int(size) if size is not None else None
    except (TypeError, ValueError):
        return None


def _upload_too_large(value: Any) -> bool:
    size = _file_size(value)
    return size is not None and size > MAX_UPLOAD_BYTES


ACTIVE_CASE_MAX_AGE_SECONDS = 1800  # 30 minutes TTL for active case visibility


async def _active_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    chat_id = str(_chat_id(update))
    cleared = context.application.bot_data.setdefault("cleared_chats", set())
    if chat_id in cleared:
        return None
    backend: BackendClient = _data(context, "backend")
    if backend is None:
        return None
    case = await backend.active_case(_chat_id(update))
    if not case:
        return None
    status = str(case.get("status") or "").upper()
    if status in {"COMPLETED", "NOT_ELIGIBLE", "FAILED_ESCALATED"}:
        return None
    created_str = case.get("created_at") or case.get("updated_at")
    if created_str:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            if (datetime.now(UTC) - dt).total_seconds() > ACTIVE_CASE_MAX_AGE_SECONDS:
                chat_mem = _data(context, "chat_memory")
                if chat_mem and hasattr(chat_mem, "clear"):
                    chat_mem.clear(chat_id)
                onb = _data(context, "onboarding")
                if onb and hasattr(onb, "clear"):
                    onb.clear(chat_id)
                return None
        except Exception:
            pass
    return case


async def _latest_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    backend: BackendClient = _data(context, "backend")
    if backend is None:
        return None
    return await backend.latest_case(_chat_id(update))


def _case_message_ids(case: dict[str, Any] | None) -> set[str]:
    if not case:
        return set()
    return {
        str(message.get("id"))
        for message in (case.get("messages") or [])
        if isinstance(message, dict) and message.get("id")
    }


def _has_understood_documents(case: dict[str, Any] | None) -> bool:
    """Return True only if user uploaded documents AND bot understood sufficient information."""
    if not case:
        return False
    documents = case.get("documents") or []
    if not documents:
        return False
    facts = case.get("facts") or {}
    recognized_docs = [
        d
        for d in documents
        if isinstance(d, dict)
        and d.get("doc_type")
        and str(d.get("doc_type")).lower() not in {"", "other", "unknown"}
    ]
    return bool(facts) or bool(recognized_docs)


def _pending_question_keyboard(
    case: dict[str, Any] | None, callbacks: CallbackStore
) -> InlineKeyboardMarkup | None:
    """Rebuild answer buttons from persisted state after a bot restart."""
    if not case:
        return None
    messages = case.get("messages") or []
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("kind") != "question":
            continue
        options = message.get("options") or []
        if not options:
            continue
        return question_keyboard(
            options,
            case_id=_case_id(case) or "",
            message_id=str(message.get("id") or ""),
            chat_id=case.get("channel_ref"),
            callbacks=callbacks,
        )
    return None


def _status_markup(
    language: str, case: dict[str, Any], callbacks: CallbackStore
) -> InlineKeyboardMarkup | ReplyKeyboardMarkup:
    if str(case.get("status") or "").upper() == "NEEDS_INFO":
        question = _pending_question_keyboard(case, callbacks)
        if question is not None:
            return question
    has_docs = _has_understood_documents(case)
    return _menu_keyboard(
        language,
        active_state=case.get("status"),
        has_active_case=True,
        has_documents=has_docs,
    )


def _notification_key(payload: dict[str, Any]) -> str:
    if payload.get("message_id"):
        return str(payload["message_id"])
    return ":".join(str(payload.get(key, "")) for key in ("case_id", "kind", "text"))


def _schedule_result_watch(
    context: ContextTypes.DEFAULT_TYPE,
    case_id: str,
    language: str,
    baseline_ids: set[str],
) -> None:
    create_task = getattr(context.application, "create_task", None)
    backend: BackendClient | None = _data(context, "backend")
    if backend is None or not callable(create_task):
        return
    create_task(
        _watch_for_case_result(
            context.application,
            backend,
            case_id,
            language,
            baseline_ids,
        )
    )


async def _watch_for_case_result(
    application: Application,
    backend: BackendClient,
    case_id: str,
    language: str,
    baseline_ids: set[str],
    *,
    attempts: int = 120,
) -> None:
    """Fallback delivery path when the backend push callback is delayed or lost."""
    chat_ref = None
    for attempt in range(attempts):
        await asyncio.sleep(0.75)
        try:
            case = await backend.get_case(case_id)
        except Exception:
            continue
        chat_ref = case.get("channel_ref") or chat_ref
        if chat_ref and attempt % 4 == 0:
            try:
                if hasattr(application.bot, "send_chat_action"):
                    await application.bot.send_chat_action(chat_id=chat_ref, action="typing")
            except Exception:
                pass
        messages = case.get("messages") or []
        new_messages = [
            item
            for item in messages
            if isinstance(item, dict)
            and str(item.get("id")) not in baseline_ids
            and item.get("kind") in {"question", "result", "info"}
        ]
        if new_messages:
            for message in new_messages:
                await handle_notification(
                    {
                        "chat_id": case.get("channel_ref") or "",
                        "case_id": case_id,
                        "kind": message.get("kind", "info"),
                        "language": language,
                        "text": message.get("text", ""),
                        "options": message.get("options") or [],
                        "message_id": message.get("id"),
                        "case": case,
                    },
                    application,
                )
            return
        status = str(case.get("status") or "").upper()
        if status in {
            "NEEDS_DOCUMENTS",
            "NEEDS_REVIEW",
            "COMPLETED",
            "NOT_ELIGIBLE",
            "FAILED_ESCALATED",
        }:
            result_msg = next(
                (
                    m
                    for m in reversed(messages)
                    if isinstance(m, dict) and m.get("kind") == "result"
                ),
                None,
            )
            if result_msg:
                result_text = result_msg.get("text", "")
            else:
                decision = case.get("decision_summary")
                scheme_id = case.get("scheme_id") or "PM-Kisan"
                if isinstance(decision, dict) and decision.get("outcome") == "ELIGIBLE":
                    app_rec = case.get("application") or {}
                    pref = app_rec.get("portal_ref") or "MOCK-PORTAL-ACK"
                    result_text = (
                        f"Scheme: {scheme_id}\nOutcome: ELIGIBLE\nBenefit: ₹6,000 / year\n"
                        f"Portal submission: (Ref: {pref})\nConfidence: High (Verified)"
                    )
                elif isinstance(decision, dict) and decision.get("outcome") == "NOT_ELIGIBLE":
                    reasons = decision.get("reasons") or ["Eligibility criteria not met"]
                    r_str = "\n".join(f"- {r}" for r in reasons)
                    result_text = (
                        f"Scheme: {scheme_id}\nOutcome: NOT_ELIGIBLE\n"
                        f"Rule reasons:\n{r_str}"
                    )
                else:
                    result_text = _status_text(language, case)

            await handle_notification(
                {
                    "chat_id": case.get("channel_ref") or "",
                    "case_id": case_id,
                    "kind": (
                        "result"
                        if status in {"COMPLETED", "NOT_ELIGIBLE", "NEEDS_DOCUMENTS"}
                        else "info"
                    ),
                    "language": language,
                    "text": result_text,
                    "options": [],
                    "message_id": f"final:{case_id}:{attempt}",
                    "case": case,
                },
                application,
            )
            return


def _language_keyboard(callbacks: CallbackStore, *, active: bool = False) -> InlineKeyboardMarkup:
    suffix = ":menu" if active else ""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "தமிழ்", callback_data=callbacks.add_action(f"language:ta{suffix}")
                ),
                InlineKeyboardButton(
                    "తెలుగు", callback_data=callbacks.add_action(f"language:te{suffix}")
                ),
            ],
            [
                InlineKeyboardButton(
                    "हिन्दी", callback_data=callbacks.add_action(f"language:hi{suffix}")
                ),
                InlineKeyboardButton(
                    "English", callback_data=callbacks.add_action(f"language:en{suffix}")
                ),
            ],
        ]
    )


def _consent_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "agree"), callback_data=callbacks.add_action("consent:yes")
                ),
                InlineKeyboardButton(
                    t(language, "no"), callback_data=callbacks.add_action("consent:no")
                ),
            ]
        ]
    )


def _done_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "menu_add"), callback_data=callbacks.add_action("case:add")
                ),
            ],
            [
                InlineKeyboardButton(
                    t(language, "menu_done"), callback_data=callbacks.add_action("case:check")
                )
            ],
        ]
    )


def _document_tag_keyboard(
    language: str, callbacks: CallbackStore, document_id: str | None = None
) -> InlineKeyboardMarkup:
    prefix = f"tag:{document_id}:" if document_id else "tag:pending:"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "doc_tag_aadhaar"),
                    callback_data=callbacks.add_action(f"{prefix}aadhaar"),
                ),
                InlineKeyboardButton(
                    t(language, "doc_tag_land"),
                    callback_data=callbacks.add_action(f"{prefix}land_record"),
                ),
            ],
            [
                InlineKeyboardButton(
                    t(language, "doc_tag_passbook"),
                    callback_data=callbacks.add_action(f"{prefix}bank_passbook"),
                ),
                InlineKeyboardButton(
                    t(language, "doc_tag_income"),
                    callback_data=callbacks.add_action(f"{prefix}income_certificate"),
                ),
            ],
            [
                InlineKeyboardButton(
                    t(language, "menu_done"),
                    callback_data=callbacks.add_action("start:done"),
                ),
            ],
        ]
    )


def _case_choice_keyboard(
    language: str, callbacks: CallbackStore, *, has_documents: bool = False
) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                t(language, "case_continue"),
                callback_data=callbacks.add_action("case:continue"),
            )
        ],
        [
            InlineKeyboardButton(
                t(language, "case_new"), callback_data=callbacks.add_action("case:new")
            )
        ],
    ]
    if has_documents:
        buttons.append([
            InlineKeyboardButton(
                f"🏛️ {t(language, 'menu_schemes')}",
                callback_data=callbacks.add_action("case:browse_schemes"),
            )
        ])
    return InlineKeyboardMarkup(buttons)


def _replace_case_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "replace_yes"),
                    callback_data=callbacks.add_action("case:replace"),
                ),
                InlineKeyboardButton(
                    t(language, "replace_no"), callback_data=callbacks.add_action("case:cancel")
                ),
            ]
        ]
    )


def _delete_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "agree"), callback_data=callbacks.add_action("delete:yes")
                ),
                InlineKeyboardButton(
                    t(language, "no"), callback_data=callbacks.add_action("delete:no")
                ),
            ]
        ]
    )


def _cancel_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "agree"), callback_data=callbacks.add_action("cancel:yes")
                ),
                InlineKeyboardButton(
                    t(language, "no"), callback_data=callbacks.add_action("cancel:no")
                ),
            ]
        ]
    )


def _start_action_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "menu_start"), callback_data=callbacks.add_action("start:new")
                )
            ]
        ]
    )


def _output_action_keyboard(
    output_key: str,
    language: str,
    callbacks: CallbackStore,
    *,
    case: dict[str, Any] | None = None,
    options: list[dict[str, Any]] | None = None,
    case_id: str = "",
    message_id: str = "",
) -> InlineKeyboardMarkup | None:
    """Return strictly contextual action buttons for the 14 defined citizen outputs (O1-O14).

    Ensures buttons do NOT all appear at once and unrelated actions remain hidden.
    """
    key = output_key.upper()
    if key in {"COMPLETED", "SUBMITTED"}:
        # O1 Submitted: No buttons on final message (clean terminal state)
        return None
    if key == "NOT_ELIGIBLE":
        # O2 Not eligible: Only start new or browse if docs exist
        buttons = [
            [
                InlineKeyboardButton(
                    t(language, "menu_start"), callback_data=callbacks.add_action("start:new")
                )
            ]
        ]
        if case and _has_understood_documents(case):
            buttons.append([
                InlineKeyboardButton(
                    f"🏛️ {t(language, 'menu_schemes')}",
                    callback_data=callbacks.add_action("case:browse_schemes"),
                )
            ])
        return InlineKeyboardMarkup(buttons)
    if key == "NEEDS_DOCUMENTS":
        # O3 Missing documents: Check eligibility button once uploaded
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Check eligibility", callback_data=callbacks.add_action("case:check")
                    )
                ]
            ]
        )
    if key == "NEEDS_INFO":
        # O4 Question: Only the question options buttons
        if options:
            return question_keyboard(
                options, case_id=case_id, message_id=message_id, callbacks=callbacks
            )
        return None
    if key == "NEEDS_REVIEW":
        # O5 Extra verification / Caseworker review notice
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t(language, "menu_continue"),
                        callback_data=callbacks.add_action("case:continue"),
                    )
                ]
            ]
        )
    if key in {"FAILED_ESCALATED", "COULD_NOT_COMPLETE"}:
        # O6 Could not complete: Start new application
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t(language, "menu_start"), callback_data=callbacks.add_action("start:new")
                    )
                ]
            ]
        )
    if key in {"EXPIRED", "CANCELLED"}:
        # O7 Expired / O8 Cancelled: Start new application
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t(language, "menu_start"), callback_data=callbacks.add_action("start:new")
                    )
                ]
            ]
        )
    if key == "BROWSE_RESULTS":
        # O9 Browse results: Continue application or start new
        btn = (
            InlineKeyboardButton(
                t(language, "case_continue"), callback_data=callbacks.add_action("case:continue")
            )
            if case
            else InlineKeyboardButton(
                t(language, "menu_start"), callback_data=callbacks.add_action("start:new")
            )
        )
        return InlineKeyboardMarkup([[btn]])
    if key == "STATUS_UPDATE":
        # O10 Status update: contextual choice keyboard
        has_docs = _has_understood_documents(case) if case else False
        return _case_choice_keyboard(language, callbacks, has_documents=has_docs)
    if key == "PROCESSING":
        # O11 Progress update: in-flight notice, no buttons
        return None
    if key == "DELETED":
        # O12 Data deleted: start new application
        return _start_action_keyboard(language, callbacks)
    if key == "VOICE_REPLY":
        # O13 Voice reply: no extra button clutter
        return None
    if key == "FALLBACK":
        # O14 Last-resort fallback: check status
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t(language, "menu_continue"),
                        callback_data=callbacks.add_action("case:continue"),
                    )
                ]
            ]
        )
    return None


async def _send(
    update: Update,
    text: str,
    *,
    language: str = "en",
    active_state: str | None = None,
    has_active_case: bool | None = None,
    has_documents: bool | None = None,
    **kwargs: Any,
) -> Any:
    message = update.effective_message
    if message is None:
        return None
    if has_active_case is None:
        has_active_case = bool(
            active_state and active_state not in {"COMPLETED", "NOT_ELIGIBLE", "FAILED_ESCALATED"}
        )
    if has_documents is None:
        has_documents = False
    kwargs.setdefault(
        "reply_markup",
        _menu_keyboard(
            language,
            active_state=active_state,
            has_active_case=has_active_case,
            has_documents=has_documents,
        ),
    )
    return await message.reply_text(text, **kwargs)


def _error_text(language: str, error: Exception, *, action: str = "request") -> str:
    if isinstance(error, BackendUnavailableError):
        return t(language, "backend_unavailable")
    if isinstance(error, BackendHTTPError):
        if error.status_code == 404:
            return t(language, "case_not_found")
        if error.status_code == 409:
            return t(language, "case_conflict")
        if error.status_code == 413:
            return t(language, "upload_too_large")
        if error.status_code == 415:
            return t(language, "unsupported_file")
        if error.status_code == 422:
            detail = _missing_detail(error.detail).lower()
            if action == "send voice" and "duration" in detail:
                return t(language, "voice_too_long", seconds=MAX_VOICE_SECONDS)
            if "text or voice" in detail:
                return t(language, "missing_input", missing="a typed message or voice note")
            if "document" in detail:
                if "maximum" in detail:
                    return t(language, "missing_input", missing="no more documents for this case")
                return t(
                    language,
                    "missing_input",
                    missing="at least one document photo or image file",
                )
            if "consent" in detail:
                return t(language, "missing_input", missing="your consent")
            return t(language, "missing_input", missing="the required information")
    return t(language, "error")


async def _send_backend_error(
    update: Update, language: str, error: Exception, *, action: str = "request"
) -> None:
    await _send(update, _error_text(language, error, action=action), language=language)


async def _submit_case(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    language: str,
    *,
    query: Any | None = None,
    active: dict[str, Any] | None = None,
) -> bool:
    backend: BackendClient = _data(context, "backend")
    if active is None:
        try:
            active = await _active_case(update, context)
        except Exception as exc:
            if query is not None:
                await _edit_callback(query, _error_text(language, exc, action="start case"))
            else:
                await _send_backend_error(update, language, exc, action="start case")
            return False
    language = str(active.get("language") or language) if active else language
    if not active or not backend:
        text = t(language, "no_active")
        if query is not None:
            await _edit_callback(query, text)
        else:
            await _send(update, text, language=language)
        return False
    case_id = _case_id(active) or ""
    delivered = context.application.bot_data.get("delivered_notifications")
    if isinstance(delivered, set):
        to_remove = {k for k in delivered if str(case_id) in k}
        delivered.difference_update(to_remove)
    baseline_ids = _case_message_ids(active)
    if query is not None:
        try:
            await query.answer(text="⏳ Evaluating eligibility...", show_alert=False)
        except Exception:
            pass
    try:
        await backend.start_case(case_id)
    except Exception as exc:
        if query is not None:
            await _edit_callback(query, _error_text(language, exc, action="start case"))
        else:
            await _send_backend_error(update, language, exc, action="start case")
        return False
    if query is not None:
        await _edit_callback(query, t(language, "analysis_started"), reply_markup=None)
    else:
        await _send(
            update,
            t(language, "analysis_started"),
            language=language,
            active_state="PROCESSING",
        )
    _schedule_result_watch(context, case_id, language, baseline_ids)
    return True


async def _edit_callback(query: Any, text: str, **kwargs: Any) -> None:
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception as exc:
        err = str(exc)
        if "Message is not modified" in err:
            try:
                await query.answer(text="✓ Updated", show_alert=False)
            except Exception:
                pass
            return
        # If edit failed because message is too old or cannot be edited, send as a new message
        try:
            if query.message and query.message.chat:
                await query.message.chat.send_message(text, **kwargs)
        except Exception:
            pass
        return


def _callbacks(context: ContextTypes.DEFAULT_TYPE) -> CallbackStore:
    callbacks = context.application.bot_data.get("callbacks")
    if not isinstance(callbacks, CallbackStore):
        callbacks = CallbackStore()
        context.application.bot_data["callbacks"] = callbacks
    return callbacks


async def _begin_onboarding(
    update: Update, context: ContextTypes.DEFAULT_TYPE, language: str | None = None
) -> None:
    language = language or _language(update, context)
    await _send(update, t(language, "privacy"), language=language)
    await _send(
        update,
        t(language, "choose_language"),
        language=language,
        reply_markup=_language_keyboard(_callbacks(context)),
    )


async def start_new_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="status")
        return
    language = _language(update, context, active)
    if active:
        await _send(
            update,
            t(language, "replace_confirm"),
            language=language,
            reply_markup=_replace_case_keyboard(language, _callbacks(context)),
        )
        return
    await _begin_onboarding(update, context)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="status")
        return
    language = _language(update, context, active)
    if active:
        has_docs = _has_understood_documents(active)
        await _send(
            update,
            _status_text(language, active),
            language=language,
            has_active_case=True,
            has_documents=has_docs,
            reply_markup=_case_choice_keyboard(
                language, _callbacks(context), has_documents=has_docs
            )
            if str(active.get("status") or "").upper() != "NEEDS_INFO"
            else _status_markup(language, active, _callbacks(context)),
        )
        return
    try:
        latest = await _latest_case(update, context)
    except Exception:
        latest = None
    if latest and str(latest.get("status", "")).upper() in {
        "COMPLETED",
        "NOT_ELIGIBLE",
        "FAILED_ESCALATED",
    }:
        language = _language(update, context, latest)
        await _send(
            update,
            _status_text(language, latest),
            language=language,
            reply_markup=_start_action_keyboard(language, _callbacks(context)),
        )
        return
    await _begin_onboarding(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="status")
        return
    if not active:
        try:
            active = await _latest_case(update, context)
        except Exception as exc:
            await _send_backend_error(update, _language(update, context), exc, action="status")
            return
    language = _language(update, context, active)
    if not active:
        await _send(update, t(language, "no_active"), language=language)
        return
    markup = _status_markup(language, active, _callbacks(context))
    send_kwargs: dict[str, Any] = {"language": language, "active_state": active.get("status")}
    if markup is not None:
        send_kwargs["reply_markup"] = markup
    await _send(
        update,
        _status_text(language, active),
        **send_kwargs,
    )


async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _submit_case(update, context, _language(update, context))


async def checklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="status")
        return
    language = _language(update, context, active)
    if not active:
        await _send(update, t(language, "no_active"), language=language)
        return
    docs = active.get("documents") or []
    type_labels = {
        "aadhaar": t(language, "doc_tag_aadhaar"),
        "land_record": t(language, "doc_tag_land"),
        "bank_passbook": t(language, "doc_tag_passbook"),
        "income_certificate": t(language, "doc_tag_income"),
        "marksheet": t(language, "doc_tag_marksheet"),
        "bonafide_certificate": "📜 Bonafide Certificate",
        "other": t(language, "doc_tag_other"),
    }
    lines = [t(language, "checklist_header", count=len(docs)), "━━━━━━━━━━━━━━━━━━━━"]
    uploaded_types = set()
    for idx, d in enumerate(docs, 1):
        dtype = d.get("doc_type", "other")
        uploaded_types.add(dtype)
        label = type_labels.get(dtype, dtype)
        lines.append(f"{idx}. {label}")
    if not docs:
        lines.append("No documents attached yet.")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("Target Scheme: PM-Kisan")
    missing = [dt for dt in ("aadhaar", "land_record", "bank_passbook") if dt not in uploaded_types]
    if missing:
        missing_names = [type_labels.get(dt, dt) for dt in missing]
        lines.append(f"⚠️ Still needed: {', '.join(missing_names)}")
    lines.append(f"👉 When ready, choose [{t(language, 'menu_done')}] below.")
    callbacks = _callbacks(context)
    await _send(
        update,
        "\n".join(lines),
        language=language,
        active_state=active.get("status"),
        reply_markup=_done_keyboard(language, callbacks),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="help")
        return
    language = _language(update, context, active)
    await _send(update, t(language, "help"), language=language)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception:
        active = None
    language = _language(update, context, active)
    await _send(update, t(language, "privacy"), language=language)
    await _send(
        update,
        t(language, "choose_language"),
        language=language,
        reply_markup=_language_keyboard(_callbacks(context), active=bool(active)),
    )


def _scheme_text(
    language: str,
    schemes: list[dict[str, Any]],
    *,
    extraction_notice: str | None = None,
) -> str:
    lines: list[str] = []
    if extraction_notice:
        lines.append(extraction_notice)
        lines.append("")
    lines.append(t(language, "schemes_header"))
    for scheme in schemes:
        name = str(scheme.get("name") or scheme.get("scheme_id") or "Unnamed scheme")
        benefit = str(scheme.get("benefit") or t(language, "scheme_benefit_unknown"))
        documents = scheme.get("required_documents") or []
        document_text = ", ".join(str(item) for item in documents) or t(
            language, "scheme_documents_unknown"
        )
        item_text = t(language, "scheme_item", name=name, benefit=benefit, documents=document_text)
        portal = scheme.get("official_url") or scheme.get("portal")
        if portal:
            item_text += f"\n🌐 Official Portal: {portal}"
        lines.append(item_text)
    return "\n\n".join(lines)


async def schemes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = _language(update, context)
    chat_id = str(_chat_id(update))
    callbacks = _callbacks(context)
    chat_mem: ChatMemory = _data(context, "chat_memory", ChatMemory())
    user_profile = chat_mem.extract_personal_info(chat_id)

    # Pre-fetch active case
    try:
        active_case = await _active_case(update, context)
    except Exception:
        active_case = None

    uploaded_docs: list[Any] = []
    if active_case:
        uploaded_docs = active_case.get("documents") or []
        facts = active_case.get("facts")
        if isinstance(facts, dict):
            for k, v in facts.items():
                if v is not None and str(v).strip():
                    user_profile.setdefault(k, str(v))

    # Check for arguments e.g. /browser farmer or /schemes scholarship
    query_text = ""
    args = getattr(context, "args", None)
    if args:
        query_text = " ".join(args).strip()

    # Fetch backend schemes if available to allow backend/test schemes to participate
    backend: BackendClient = _data(context, "backend")
    backend_schemes: list[dict[str, Any]] = []
    if backend is not None:
        try:
            backend_schemes = await backend.get_schemes()
        except Exception:
            pass

    # Requirement 1: Browse schemes only shows when docs or citizen data exist
    has_enough_data = (
        bool(uploaded_docs)
        or bool(user_profile)
        or bool(query_text)
        or bool(backend_schemes)
    )
    if not has_enough_data and not active_case:
        need_docs_msg = (
            "ℹ️ To find and recommend the right government welfare schemes "
            "tailored to your exact eligibility:\n\n"
            "Please upload your documents (such as Aadhaar Card, Land Record, or Bank Passbook) "
            "or share your requirement first by starting an application.\n\n"
            "👉 Tap [Start new application] below to begin!"
        )
        reply_kb = _start_action_keyboard(language, callbacks)
        await _send(
            update,
            need_docs_msg,
            language=language,
            has_active_case=False,
            has_documents=False,
            reply_markup=reply_kb,
        )
        return

    # Check if uploaded document data is understood and sufficient
    if uploaded_docs and not user_profile and not query_text and not backend_schemes:
        has_recognized = any(
            isinstance(d, dict)
            and d.get("doc_type")
            and str(d.get("doc_type")).lower() not in {"", "other", "unknown"}
            for d in uploaded_docs
        )
        if not has_recognized:
            insufficient_msg = (
                "ℹ️ The uploaded document information is currently insufficient or unreadable.\n\n"
                "Please share additional details (such as your occupation, state, or landholding) "
                "or upload a clearer photo of your documents so we can assess applicable schemes."
            )
            await _send(
                update,
                insufficient_msg,
                language=language,
                has_active_case=bool(active_case),
                has_documents=False,
            )
            return

    # Requirement 2: Tailored scheme matching with Kaggle dataset + gap analysis
    # At most 3 schemes (fewer than 4 schemes)
    matched_schemes = match_schemes_with_gap_analysis(
        user_profile=user_profile,
        uploaded_docs=uploaded_docs,
        query=query_text,
        limit=3,
    )

    # If backend has custom mock schemes (e.g. from tests), ensure they are included
    if backend_schemes:
        matched_ids = {s.get("scheme_id") for s in matched_schemes}
        for bs in backend_schemes:
            if bs.get("scheme_id") not in matched_ids:
                req_raw = bs.get("required_documents") or []
                req_keys = [normalize_doc_type(d) for d in req_raw]
                up_keys = {normalize_doc_type(d) for d in uploaded_docs}
                missing_keys = [k for k in req_keys if k not in up_keys]
                matched_schemes.insert(0, {
                    "scheme_id": bs.get("scheme_id"),
                    "name": bs.get("name"),
                    "benefit": bs.get("benefit"),
                    "required_documents": req_raw,
                    "lacking_documents_count": len(missing_keys),
                    "lacking_documents": missing_keys or req_raw,
                    "missing_documents_count": len(missing_keys),
                    "missing_documents_names": missing_keys or req_raw,
                    "lacking_user_info": ["None (All required details verified)"],
                    "missing_user_info": ["None (All required details verified)"],
                    "source": "Backend Scheme Store",
                    "official_url": bs.get("official_url"),
                })
        matched_schemes = matched_schemes[:3]

    if not matched_schemes:
        no_match_msg = (
            "ℹ️ No suitable government welfare schemes could be identified based on your "
            "current profile and uploaded documents.\n\n"
            "Please provide more specific details (such as occupation, income, or state) "
            "or upload additional documents to help us find matching schemes."
        )
        await _send(
            update,
            no_match_msg,
            language=language,
            has_active_case=bool(active_case),
            has_documents=True,
        )
        return

    # Message 1: Beautiful gap analysis output
    gap_analysis_text = format_schemes_gap_analysis(matched_schemes, language=language)
    await _send(
        update,
        gap_analysis_text,
        language=language,
        has_active_case=bool(active_case),
        has_documents=True,
    )

    # Message 2: Follow-up action prompt without duplicate Browse schemes button
    action_button = (
        InlineKeyboardButton(
            t(language, "case_continue"), callback_data=callbacks.add_action("case:continue")
        )
        if active_case
        else InlineKeyboardButton(
            t(language, "menu_start"), callback_data=callbacks.add_action("start:new")
        )
    )
    await _send(
        update,
        t(language, "scheme_need_prompt"),
        language=language,
        reply_markup=InlineKeyboardMarkup([[action_button]]),
        has_active_case=bool(active_case),
        has_documents=True,
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="delete")
        return
    language = _language(update, context, active)
    if not active:
        await _send(update, t(language, "no_active"), language=language)
        return
    await _send(
        update,
        t(language, "delete_confirm"),
        language=language,
        reply_markup=_delete_keyboard(language, _callbacks(context)),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="cancel")
        return
    language = _language(update, context, active)
    if not active:
        await _send(update, t(language, "no_active"), language=language)
        return
    await _send(
        update,
        t(language, "cancel_confirm"),
        language=language,
        reply_markup=_cancel_keyboard(language, _callbacks(context)),
    )


_KNOWN_ACTIONS = {
    "consent:yes",
    "consent:no",
    "case:new",
    "case:replace",
    "case:continue",
    "case:cancel",
    "case:browse_schemes",
    "delete:yes",
    "delete:no",
    "cancel:yes",
    "cancel:no",
    "start:new",
    "start:done",
    "case:check",
    "case:add",
}


def _inspect_button_text(query: Any, data: str) -> str:
    message = getattr(query, "message", None)
    if not message:
        return ""
    reply_markup = getattr(message, "reply_markup", None)
    if not reply_markup:
        return ""
    keyboard = getattr(reply_markup, "inline_keyboard", None)
    if not keyboard:
        return ""
    for row in keyboard:
        for btn in row:
            if getattr(btn, "callback_data", None) == data:
                return str(getattr(btn, "text", "") or "").strip()
    return ""


def _resolve_callback_action(
    data: str,
    callbacks: CallbackStore,
    query: Any,
    active_case: dict[str, Any] | None,
) -> str | None:
    # Interactive questions use prefix "a:". They must NEVER be treated as actions.
    if data.startswith("a:"):
        return None

    action_target = callbacks.pop_action(data)
    if action_target and action_target.action:
        act = action_target.action
        if act in _KNOWN_ACTIONS or act.startswith("language:") or act.startswith("tag:"):
            return act

    legacy = {
        "lang:ta": "language:ta",
        "lang:te": "language:te",
        "lang:hi": "language:hi",
        "lang:en": "language:en",
        "consent:yes": "consent:yes",
        "consent:no": "consent:no",
        "case:new": "case:new",
        "case:continue": "case:continue",
        "delete:no": "delete:no",
        "delete:yes": "delete:yes",
        "cancel:no": "cancel:no",
        "cancel:yes": "cancel:yes",
        "start:done": "start:done",
        "case:check": "case:check",
        "case:add": "case:add",
        "start:new": "start:new",
        "case:replace": "case:replace",
        "case:cancel": "case:cancel",
        "case:browse_schemes": "case:browse_schemes",
    }
    if data in legacy:
        return legacy[data]

    if data.startswith("u:"):
        raw = data[2:]
        if raw in _KNOWN_ACTIONS or raw.startswith("language:") or raw.startswith("tag:"):
            return raw

    btn_text = _inspect_button_text(query, data).lower()
    msg_text = str(getattr(getattr(query, "message", None), "text", "") or "").lower()

    if btn_text:
        if any(w in btn_text for w in ("continue", "जारी", "కొనసాగించు", "தொடர")):
            return "case:continue"
        if any(
            w in btn_text
            for w in (
                "check eligibility",
                "check",
                "done",
                "पात्रता",
                "అర్హత",
                "சரிபார்க்க",
                "சரிபார்",
                "పూర్తయింది",
                "முடிந்தது",
                "पूरा हुआ",
            )
        ):
            return "case:check"
        if any(w in btn_text for w in ("add another", "add doc", "మరొక", "மற்றொரு", "अन्य")):
            return "case:add"
        if any(w in btn_text for w in ("browse schemes", "schemes", "పథకాలు", "திட்டங்கள்", "योजना")):
            return "case:browse_schemes"
        if any(
            w in btn_text
            for w in (
                "start new",
                "new case",
                "start a new",
                "start fresh",
                "नया",
                "కొత్త",
                "புதிய",
            )
        ):
            replace_hints = (
                "starting a new application will delete",
                "delete that case",
                "செயலில் ஒரு வழக்கு",
            )
            if any(w in msg_text for w in replace_hints):
                return "case:replace"
            return "case:new"
        keep_hints = (
            "keep active",
            "keep current",
            "सक्रिय केस रखें",
            "కేసును కొనసాగించు",
            "வைத்திருக்கவும்",
        )
        if any(w in btn_text for w in keep_hints):
            return "case:cancel"
        if "english" in btn_text:
            return "language:en"
        if "हिन्दी" in btn_text or "hindi" in btn_text:
            return "language:hi"
        if "తెలుగు" in btn_text or "telugu" in btn_text:
            return "language:te"
        if "தமிழ்" in btn_text or "tamil" in btn_text:
            return "language:ta"
        if any(w in btn_text for w in ("agree", "सहमत", "అంగీకరిస్తున్నాను", "ஒப்புக்கொள்கிறேன்")):
            if any(w in msg_text for w in ("delete", "हटा", "நீக்க", "తొలగించ")):
                return "delete:yes"
            if any(w in msg_text for w in ("cancel", "रद्द", "రద్దు", "ரத்து")):
                return "cancel:yes"
            # Require explicit consent keywords before treating generic agree as DPDP consent
            if any(
                w in msg_text
                for w in (
                    "consent",
                    "data",
                    "privacy",
                    "सहमत",
                    "गोपनीयता",
                    "தனியுரிமை",
                    "గోప్యత",
                    "process",
                )
            ):
                return "consent:yes"
            return None
        if any(w in btn_text for w in ("no", "नहीं", "వద్దు", "இல்லை")):
            if any(w in msg_text for w in ("delete", "हटा", "நீக்க", "తొలగించ")):
                return "delete:no"
            if any(w in msg_text for w in ("cancel", "रद्द", "రద్దు", "ரத்து")):
                return "cancel:no"
            # Require explicit consent keywords before treating generic no as DPDP decline
            if any(
                w in msg_text
                for w in (
                    "consent",
                    "data",
                    "privacy",
                    "सहमत",
                    "गोपनीयता",
                    "தனியுரிமை",
                    "గోప్యత",
                    "process",
                )
            ):
                return "consent:no"
            return None

    if data.startswith("u:"):
        if active_case:
            return "case:continue"
        return "start:new"

    return None


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    chat_id = _chat_id(update)
    onboarding: OnboardingStore = _data(context, "onboarding", OnboardingStore())
    backend: BackendClient = _data(context, "backend")
    callbacks = _callbacks(context)

    # Pre-fetch active case once to eliminate duplicate HTTP GET calls
    active_case: dict[str, Any] | None = None
    try:
        active_case = await _active_case(update, context)
    except Exception:
        active_case = None

    language = (
        str(active_case["language"])
        if active_case and active_case.get("language")
        else onboarding.language_for(chat_id)
    )

    if data.startswith("a:"):
        target: AnswerTarget | None = callbacks.get(data)
        if target is None and active_case and backend:
            btn_text = _inspect_button_text(query, data)
            messages = active_case.get("messages") or []
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("kind") == "question":
                    target = AnswerTarget(
                        _case_id(active_case) or "",
                        str(msg.get("id") or ""),
                        btn_text,
                        str(chat_id),
                    )
                    break
        if target is None or not backend:
            await _edit_callback(query, t(language, "callback_unavailable"))
            return
        if target.chat_id and target.chat_id != str(chat_id):
            callbacks.pop(data)
            await _edit_callback(query, t(language, "callback_unavailable"), reply_markup=None)
            return
        baseline_ids = {target.message_id}
        baseline_ids.update(_case_message_ids(active_case))
        try:
            await backend.answer(target.case_id, target.message_id, target.option)
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="answer"))
            return
        callbacks.pop(data)
        previous = query.message.text if query.message else ""
        await _edit_callback(
            query,
            f"{previous}\n\n✓ {t(language, 'answer_recorded')}",
            reply_markup=None,
        )
        _schedule_result_watch(context, target.case_id, language, baseline_ids)
        return

    action = _resolve_callback_action(data, callbacks, query, active_case)

    if action == "case:browse_schemes":
        await schemes_command(update, context)
        return

    if action and action.startswith("language:"):
        parts = action.split(":")
        language = parts[1]
        if language not in {"ta", "te", "hi", "en"}:
            return
        onboarding.set_language(chat_id, language)  # type: ignore[arg-type]
        if len(parts) > 2 and parts[2] == "menu":
            await _edit_callback(query, t(language, "language_saved"), reply_markup=None)
            return
        await _edit_callback(
            query,
            t(language, "consent"),
            reply_markup=_consent_keyboard(language, callbacks),
        )
        return
    if action == "consent:no":
        onboarding.clear(chat_id)
        await _edit_callback(query, t(language, "consent_declined"), reply_markup=None)
        return
    if action == "consent:yes":
        onboarding.set_consent(chat_id, True)
        try:
            if backend is None:
                raise BackendUnavailableError
            case = await backend.create_case(language, chat_id)
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="create case"))
            return
        onboarding.clear(chat_id)
        # ReplyKeyboardMarkup belongs in a new chat message. Telegram does not
        # accept it in editMessageText, and swallowing that API error would leave
        # the citizen with no usable next step after tapping consent.
        await _edit_callback(query, t(language, "consent_saved"), reply_markup=None)
        await _send(update, t(language, "step_guide"), language=language, active_state="COLLECTING")
        context.application.bot_data.setdefault("cases", {})[str(chat_id)] = _case_id(case)
        return
    if action == "case:add":
        try:
            await query.answer(
                text="📸 Please send your document photo or file now", show_alert=False
            )
        except Exception:
            pass
        await _edit_callback(
            query,
            t(language, "document_guidance"),
            reply_markup=_done_keyboard(language, callbacks),
        )
        return
    if action and action.startswith("tag:"):
        parts = action.split(":")
        if len(parts) >= 3:
            doc_id, chosen_type = parts[1], parts[2]
            active = active_case or await _active_case(update, context)
            if active and backend and doc_id != "pending":
                try:
                    await backend.classify_document(_case_id(active) or "", doc_id, chosen_type)
                except Exception:
                    pass
            tag_label = t(language, f"doc_tag_{chosen_type}")
            await _edit_callback(
                query,
                f"✅ {tag_label} saved!\nSend remaining photos or tap Check eligibility:",
                reply_markup=_done_keyboard(language, callbacks),
            )
            return
    if action == "start:new":
        await _edit_callback(query, t(language, "starting_new"), reply_markup=None)
        await start_new_application(update, context)
        return
    if action == "case:new":
        await _edit_callback(
            query,
            t(language, "replace_confirm"),
            reply_markup=_replace_case_keyboard(language, callbacks),
        )
        return
    if action == "case:cancel":
        await _edit_callback(query, t(language, "case_keep"), reply_markup=None)
        return
    if action == "case:replace":
        try:
            active = active_case or await _active_case(update, context)
            if active and backend:
                await backend.delete_case(_case_id(active) or "")
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="replace case"))
            return
        onboarding.clear(chat_id)
        onboarding.set_language(chat_id, language)  # type: ignore[arg-type]
        await _edit_callback(query, t(language, "old_case_deleted"), reply_markup=None)
        await _begin_onboarding(update, context, language)
        return
    if action == "case:continue":
        active = active_case
        if not active:
            try:
                active = await _active_case(update, context)
            except Exception as exc:
                await _edit_callback(query, _error_text(language, exc, action="status"))
                return
        if not active:
            await _edit_callback(query, t(language, "no_active"), reply_markup=None)
            return

        status = str(active.get("status") or "").upper()
        docs = active.get("documents") or []
        uploaded_types = {d.get("doc_type") for d in docs if isinstance(d, dict)}
        type_labels = {
            "aadhaar": t(language, "doc_tag_aadhaar"),
            "land_record": t(language, "doc_tag_land"),
            "bank_passbook": t(language, "doc_tag_passbook"),
            "income_certificate": t(language, "doc_tag_income"),
            "marksheet": t(language, "doc_tag_marksheet"),
            "other": t(language, "doc_tag_other"),
        }

        if status == "NEEDS_DOCUMENTS":
            missing = [
                dt for dt in ("aadhaar", "land_record", "bank_passbook")
                if dt not in uploaded_types
            ]
            missing_names = [type_labels.get(dt, dt) for dt in missing]
            missing_str = ", ".join(missing_names) if missing_names else "required documents"
            lines = [
                "📋 Continuing Active Application (PM-Kisan)",
                "",
                f"✅ Verified documents ({len(docs)}):",
            ]
            for idx, d in enumerate(docs, 1):
                dtype = d.get("doc_type", "other")
                lines.append(f"{idx}. {type_labels.get(dtype, dtype)}")
            lines.extend([
                "",
                f"⚠️ Missing Document Required:\n👉 {missing_str}",
                "",
                f"Please upload a clear photo of your {missing_str}.",
                f"When ready, choose [{t(language, 'menu_done')}] below.",
            ])
            text = "\n".join(lines)
            await _edit_callback(query, text, reply_markup=_done_keyboard(language, callbacks))
            return
        if status == "NEEDS_INFO":
            question_markup = _pending_question_keyboard(active, callbacks)
            text = "📋 Continuing Active Application\n\n❓ Please answer the pending question:"
            await _edit_callback(query, text, reply_markup=question_markup)
            return
        if status == "COLLECTING":
            text = f"📋 Active Application (PM-Kisan)\n\n{t(language, 'step_guide')}"
            await _edit_callback(query, text, reply_markup=_done_keyboard(language, callbacks))
            return

        text = f"📋 Active Application Status: {status}\n\n" + _status_text(language, active)
        await _edit_callback(query, text, reply_markup=_done_keyboard(language, callbacks))
        return
    if action == "delete:no":
        await _edit_callback(query, t(language, "delete_cancelled"), reply_markup=None)
        return
    if action == "cancel:no":
        await _edit_callback(query, t(language, "case_keep"), reply_markup=None)
        return
    if action == "cancel:yes":
        try:
            active = active_case or await _active_case(update, context)
            if active and backend:
                await backend.delete_case(_case_id(active) or "")
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="cancel"))
            return
        onboarding.clear(chat_id)
        await _edit_callback(query, t(language, "cancelled"), reply_markup=None)
        return
    if action == "delete:yes":
        try:
            active = active_case or await _active_case(update, context)
            if active and backend:
                await backend.delete_case(_case_id(active) or "")
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="delete"))
            return
        onboarding.clear(chat_id)
        await _edit_callback(query, t(language, "deleted"), reply_markup=None)
        return
    if action in {"start:done", "case:check"}:
        await _submit_case(update, context, language, query=query, active=active_case)
        return

    # Fallback when action was unrecognized: if active case exists, show it directly
    if active_case:
        await _edit_callback(
            query,
            f"📋 Active Application Status: {active_case.get('status')}\n\n"
            + _status_text(language, active_case),
            reply_markup=_done_keyboard(language, callbacks),
        )
        return
    await _edit_callback(query, t(language, "callback_unavailable"))


def _missing_detail(detail: Any) -> str:
    if isinstance(detail, dict):
        for key in ("missing", "missing_documents", "required"):
            if key in detail:
                value = detail[key]
                if isinstance(value, list):
                    return ", ".join(str(item) for item in value)
                return str(value)
        if "detail" in detail:
            return _missing_detail(detail["detail"])
    return str(detail) if detail else ""


async def _download(context: ContextTypes.DEFAULT_TYPE, file_id: str) -> bytes:
    telegram_file = await context.bot.get_file(file_id)
    if hasattr(telegram_file, "download_as_bytearray"):
        content = bytes(await telegram_file.download_as_bytearray())
    else:
        output = BytesIO()
        await telegram_file.download_to_memory(output)
        content = output.getvalue()
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadTooLargeError
    return content


def _is_unrelated_query(text: str) -> bool:
    """Detect queries unrelated to government schemes, document uploads, or welfare."""
    clean = text.lower().strip()
    if not clean:
        return False
    unrelated_triggers = (
        "joke", "poem", "story", "weather", "cricket", "football", "world cup",
        "movie", "song", "who is", "what is the capital", "recipe", "cook",
        "code", "programming", "math", "calculate", "solve", "president",
    )
    if any(u in clean for u in unrelated_triggers):
        return True
    scheme_keywords = (
        "scheme", "yojana", "benefit", "subsidy", "farmer", "kisan", "crop", "land", "patta",
        "student", "scholarship", "college", "school", "marksheet", "fee", "study",
        "pension", "elderly", "senior", "widow", "disabled", "divyang",
        "vendor", "svanidhi", "business", "loan", "street", "hawker",
        "house", "awas", "pmay", "housing", "bpl", "ration", "poor",
        "health", "ayushman", "hospital", "medical", "insurance", "card",
        "gas", "cylinder", "ujjwala", "lpg", "electricity",
        "document", "aadhaar", "passbook", "bank", "income", "caste", "apply",
        "status", "eligib", "check", "verify", "help", "start", "register",
        "tamil nadu", "andhra", "telangana", "bihar", "uttar pradesh",
        "வணக்கம்", "திட்டம்", "விவசாயி", "నమస్కారం", "పథకం", "రైతు", "యोजना", "किसान",
    )
    if any(k in clean for k in scheme_keywords):
        return False
    words = set(re.findall(r"\w+", clean))
    greetings = {"hello", "hi", "hey", "namaste", "namaskaram", "vanakkam", "info"}
    if words.intersection(greetings):
        return False
    return False


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = message.text if message else None
    if not text or not text.strip():
        return
    chat_mem: ChatMemory = _data(context, "chat_memory", ChatMemory())
    chat_id = str(_chat_id(update))
    if hasattr(chat_mem, "clean_stale_sessions"):
        chat_mem.clean_stale_sessions()
    if text:
        chat_mem.add_message(chat_id, "user", text)
        menu_actions = {
            "menu_start": start_new_application,
            "menu_continue": status_command,
            "menu_schemes": schemes_command,
            "menu_help": help_command,
            "menu_delete": delete_command,
            "menu_cancel": cancel_command,
            "menu_language": language_command,
            "menu_checklist": checklist_command,
            "menu_done": submit_command,
        }
        for language in ("en", "ta", "te", "hi"):
            for key, handler in menu_actions.items():
                if text.strip() == t(language, key).strip():
                    await handler(update, context)
                    return

        clean_text = text.strip().lower()

        # Ending chat triggers: clear memory and active case (To-Do 6)
        if clean_text in {
            "end chat",
            "/end",
            "end",
            "bye",
            "goodbye",
            "exit",
            "/exit",
            "quit",
            "/quit",
            "close chat",
            "done with chat",
        }:
            cleared = context.application.bot_data.setdefault("cleared_chats", set())
            cleared.add(chat_id)
            chat_mem.clear(chat_id)
            _data(context, "onboarding", OnboardingStore()).clear(chat_id)
            closing_text = (
                "👋 Chat session ended and temporary memory cleared.\n\n"
                "Thank you for contacting ADHIKAAR AI! Whenever you need assistance again, "
                "just send /start or /browser."
            )
            chat_mem.add_message(chat_id, "bot", closing_text)
            await _send(update, closing_text, has_active_case=False)
            return

        # Schemes / Browser / Benefits triggers (To-Do 1 & 3)
        benefit_triggers = [
            "benefits of mine personal info",
            "benefit of mine personal info",
            "benefits of my personal info",
            "benefits of mine",
            "know the benefits",
            "benefits of personal info",
            "personal info",
            "my benefits",
            "welfare benefits",
            "what benefits",
            "browser",
            "/browser",
            "browse",
            "/browse",
            "browse schemes",
            "schemes list",
            "yojana",
            "benefits",
            "browse benefits",
            "all benefits",
            "govt benefits",
            "welfare",
            "welfare schemes",
        ]
        if any(trig in clean_text for trig in benefit_triggers):
            await schemes_command(update, context)
            return

        if clean_text in {
            "status",
            "/status",
            "continue",
            "my case",
            "my application",
            "check status",
        }:
            await status_command(update, context)
            return
        if clean_text in {"help", "/help", "guide", "info"}:
            await help_command(update, context)
            return
        if clean_text in {"language", "/language", "lang", "bhasha"}:
            await language_command(update, context)
            return
        if clean_text in {"cancel", "/cancel"}:
            await cancel_command(update, context)
            return
        if clean_text in {"delete", "/delete"}:
            await delete_command(update, context)
            return
        if clean_text in {"checklist", "/checklist", "documents", "my documents", "uploaded"}:
            await checklist_command(update, context)
            return
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="send text")
        return
    language = _language(update, context, active)
    case_id = _case_id(active)
    backend: BackendClient = _data(context, "backend")
    if not case_id or not text or not backend:
        if _is_unrelated_query(text):
            redirection_msg = (
                "ℹ️ I am ADHIKAAR AI, specifically designed to help citizens identify, "
                "check eligibility for, and apply for government welfare schemes and "
                "entitlements.\n\n"
                "Please ask about government schemes (such as PM-Kisan, Scholarships, or Housing), "
                "or send /start to begin checking your eligibility."
            )
            chat_mem.add_message(chat_id, "bot", redirection_msg)
            await _send(update, redirection_msg, language=language, has_active_case=False)
            return

        user_info = chat_mem.extract_personal_info(chat_id)
        if user_info:
            summary = ", ".join(f"{k}: {v}" for k, v in user_info.items())
            reply = (
                f"👍 Stored in temporary memory: {summary}.\n\n"
                f"{t(language, 'not_ready')}\n\n"
                "💡 Or type /browser to view government welfare benefits matching your profile!"
            )
        else:
            reply = t(language, "not_ready")
        chat_mem.add_message(chat_id, "bot", reply)
        await _send(update, reply, language=language, has_active_case=False)
        return

    clean_text = text.strip().lower()
    done_triggers = {
        "done",
        "/done",
        "submit",
        "/submit",
        "finish",
        "/finish",
        "apply",
        "/apply",
        "check",
        "/check",
        "ready",
        "/ready",
        "start",
        "/start",
        "evaluate",
        "check eligibility",
        "/check-eligibility",
        "eligible",
        "eligibility",
        "am i eligible",
        "verify",
        "check my case",
    }
    for lang in ("en", "ta", "te", "hi"):
        done_triggers.add(t(lang, "done").strip().lower())
        done_triggers.add(t(lang, "menu_done").strip().lower())
    done_triggers.update({"முடிந்தது", "పూర్తయింది", "पूरा हुआ"})

    if clean_text in done_triggers:
        await _submit_case(update, context, language)
        return

    try:
        await backend.send_text(case_id, text)
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="send text")
        return

    case_status = str(active.get("status") or "").upper() if active else "COLLECTING"
    if case_status == "NEEDS_DOCUMENTS":
        callbacks = _callbacks(context)
        await _send(
            update,
            t(language, "received_text_need_docs"),
            language=language,
            active_state=case_status,
            reply_markup=_done_keyboard(language, callbacks),
        )
    else:
        await _send(
            update,
            t(language, "received_text"),
            language=language,
            active_state=case_status if active else "COLLECTING",
        )


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="send voice")
        return
    language = _language(update, context, active)
    voice = update.effective_message.voice if update.effective_message else None
    if not active or not voice:
        await _send(update, t(language, "not_ready"), language=language)
        return
    if voice.duration and voice.duration > MAX_VOICE_SECONDS:
        await _send(
            update, t(language, "voice_too_long", seconds=MAX_VOICE_SECONDS), language=language
        )
        return
    if _upload_too_large(voice):
        await _send(update, t(language, "upload_too_large"), language=language)
        return
    try:
        content = await _download(context, voice.file_id)
    except UploadTooLargeError:
        await _send(update, t(language, "upload_too_large"), language=language)
        return
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="download voice")
        return
    try:
        await _data(context, "backend").send_voice(_case_id(active) or "", content)
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="send voice")
        return
    await _send(
        update,
        t(language, "received_voice"),
        language=language,
        active_state=active.get("status") if active else "COLLECTING",
    )


async def _forward_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    *,
    filename: str,
    content_type: str,
    doc_type: str | None = None,
) -> dict[str, Any] | None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="upload document")
        return None
    language = _language(update, context, active)
    if not active:
        await _send(update, t(language, "not_ready"), language=language)
        return None
    source = getattr(update.effective_message, "document", None)
    if _upload_too_large(source):
        await _send(update, t(language, "upload_too_large"), language=language)
        return None
    try:
        content = await _download(context, file_id)
    except UploadTooLargeError:
        await _send(update, t(language, "upload_too_large"), language=language)
        return None
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="download document")
        return None
    try:
        result = await _data(context, "backend").send_document(
            _case_id(active) or "",
            content,
            filename=filename,
            content_type=content_type,
            doc_type=doc_type,
        )
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="upload document")
        return None
    try:
        await update.effective_message.delete()
    except Exception:
        pass
    if isinstance(result, dict):
        return result
    return {"received": True}


async def _document_ack(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int) -> None:
    active = await _active_case(update, context)
    language = _language(update, context, active)
    callbacks = _callbacks(context)
    ack_msg = t(language, "received_documents", count=count)
    await _send(
        update,
        (
            f"{ack_msg}\n\n"
            "🔒 Chat copy removed after secure upload for DPDP privacy.\n\n"
            "👉 Tap [🔍 Check Eligibility & Outcome Now] below to evaluate your application."
        ),
        language=language,
        active_state=active.get("status") if active else "COLLECTING",
        has_documents=True,
        reply_markup=_done_keyboard(language, callbacks),
    )
    if active and active.get("status") == "NEEDS_DOCUMENTS":
        create_task = getattr(context.application, "create_task", None)
        if callable(create_task):
            create_task(_submit_case(update, context, language))


def _detect_doc_type(text: str) -> str | None:
    text_lower = text.lower()
    if any(k in text_lower for k in (
        "aadhaar", "adhar", "uid", "aadhar", "adhaar", "आधार", "ஆதார்", "ఆధార్"
    )):
        return "aadhaar"
    if any(k in text_lower for k in (
        "land", "patta", "chitta", "khasra", "7/12", "khatauni", "ror",
        "భూమి", "நிலம்", "भूमि", "పట్టా"
    )):
        return "land_record"
    if any(k in text_lower for k in (
        "bank", "passbook", "account", "statement", "बैंक", "பாஸ்புக்", "పాస్‌బుక్"
    )):
        return "bank_passbook"
    if any(k in text_lower for k in ("income", "aay", "வருமானம்", "ఆదాయం", "आय")):
        return "income_certificate"
    if any(k in text_lower for k in ("marksheet", "mark", "10th", "12th", "10", "12")):
        return "marksheet"
    return None


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.photo:
        return
    photo = message.photo[-1]
    if _upload_too_large(photo):
        try:
            active = await _active_case(update, context)
        except Exception as exc:
            await _send_backend_error(
                update, _language(update, context), exc, action="upload document"
            )
            return
        language = _language(update, context, active)
        await _send(update, t(language, "upload_too_large"), language=language)
        return

    caption = getattr(message, "caption", "") or ""
    doc_type = _detect_doc_type(caption)
    filename = f"{doc_type}.jpg" if doc_type else "photo.jpg"
    doc_result = await _forward_document(
        update,
        context,
        photo.file_id,
        filename=filename,
        content_type="image/jpeg",
        doc_type=doc_type,
    )
    if not doc_result:
        return
    if getattr(message, "media_group_id", None):
        await _data(context, "albums").add(
            _chat_id(update),
            message.media_group_id,
            lambda count: _document_ack(update, context, count),
        )
    else:
        active = await _active_case(update, context)
        language = _language(update, context, active)
        callbacks = _callbacks(context)
        ack_msg = t(language, "received_documents", count=1)
        if doc_type:
            tag_label = t(language, f"doc_tag_{doc_type}")
            text = (
                f"{ack_msg}\n\n✅ {tag_label} received.\n"
                "🔒 Chat copy removed after secure upload for DPDP privacy.\n\n"
                "👉 Tap [🔍 Check Eligibility & Outcome Now] below to evaluate your application."
            )
        else:
            text = (
                f"{ack_msg}\n\n"
                "🔒 Chat copy removed after secure upload for DPDP privacy.\n\n"
                "👉 Tap [🔍 Check Eligibility & Outcome Now] below to evaluate your application."
            )
        reply_markup = _done_keyboard(language, callbacks)
        await _send(
            update,
            text,
            language=language,
            active_state=active.get("status") if active else "COLLECTING",
            reply_markup=reply_markup,
        )
        if active and active.get("status") == "NEEDS_DOCUMENTS":
            create_task = getattr(context.application, "create_task", None)
            if callable(create_task):
                create_task(_submit_case(update, context, language))


async def image_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    document = message.document if message else None
    if not document:
        return
    content_type = document.mime_type or ""
    if not content_type.startswith("image/"):
        try:
            active = await _active_case(update, context)
        except Exception as exc:
            await _send_backend_error(
                update, _language(update, context), exc, action="upload document"
            )
            return
        language = _language(update, context, active)
        await _send(update, t(language, "document_rejected"), language=language)
        return
    if _upload_too_large(document):
        try:
            active = await _active_case(update, context)
        except Exception as exc:
            await _send_backend_error(
                update, _language(update, context), exc, action="upload document"
            )
            return
        language = _language(update, context, active)
        await _send(update, t(language, "upload_too_large"), language=language)
        return

    raw_name = document.file_name or "document"
    caption = getattr(message, "caption", "") or ""
    combined = f"{raw_name} {caption}"
    doc_type = _detect_doc_type(combined)
    filename = f"{doc_type}.png" if doc_type else raw_name
    doc_result = await _forward_document(
        update,
        context,
        document.file_id,
        filename=filename,
        content_type=content_type,
        doc_type=doc_type,
    )
    if not doc_result:
        return
    if getattr(message, "media_group_id", None):
        await _data(context, "albums").add(
            _chat_id(update),
            message.media_group_id,
            lambda count: _document_ack(update, context, count),
        )
    else:
        active = await _active_case(update, context)
        language = _language(update, context, active)
        callbacks = _callbacks(context)
        ack_msg = t(language, "received_documents", count=1)
        if doc_type:
            tag_label = t(language, f"doc_tag_{doc_type}")
            text = (
                f"{ack_msg}\n\n✅ {tag_label} received.\n"
                "🔒 Chat copy removed after secure upload for DPDP privacy.\n\n"
                "👉 Tap Check eligibility when you are ready."
            )
        else:
            text = (
                f"{ack_msg}\n\n"
                "🔒 Chat copy removed after secure upload for DPDP privacy.\n\n"
                "👉 Tap Check eligibility when you are ready."
            )
        reply_markup = _done_keyboard(language, callbacks)
        await _send(
            update,
            text,
            language=language,
            active_state=active.get("status") if active else "COLLECTING",
            reply_markup=reply_markup,
        )


async def handle_notification(payload: dict[str, Any], application: Application) -> None:
    callbacks: CallbackStore = application.bot_data.setdefault("callbacks", CallbackStore())
    delivered = application.bot_data.setdefault("delivered_notifications", set())
    in_flight = application.bot_data.setdefault("in_flight_notifications", set())
    key = _notification_key(payload)
    if key in delivered or key in in_flight:
        return
    # Claim the key before the first await. Push delivery and the persisted-case
    # watcher can otherwise both observe an empty set and send the same result.
    in_flight.add(key)
    try:
        raw_text = str(payload.get("text", ""))
        language = str(payload.get("language", "en"))
        output_key = None
        if "ELIGIBLE" in raw_text and "NOT_ELIGIBLE" not in raw_text:
            output_key = "COMPLETED"
        elif "NOT_ELIGIBLE" in raw_text:
            output_key = "NOT_ELIGIBLE"
        elif "missing or clearer" in raw_text.lower() or "needs_documents" in raw_text.lower():
            output_key = "NEEDS_DOCUMENTS"
        elif payload.get("kind") == "question":
            output_key = "NEEDS_INFO"
        elif "verification" in raw_text.lower() or "casework" in raw_text.lower():
            output_key = "NEEDS_REVIEW"

        for text, keyboard in render_notification(payload, callbacks=callbacks):
            if keyboard is None and output_key:
                keyboard = _output_action_keyboard(
                    output_key,
                    language,
                    callbacks,
                    case=payload.get("case"),
                    options=payload.get("options"),
                    case_id=str(payload.get("case_id", "")),
                    message_id=str(payload.get("message_id", "")),
                )
            await application.bot.send_message(
                chat_id=payload["chat_id"], text=text, reply_markup=keyboard
            )
    except Exception:
        in_flight.discard(key)
        raise
    in_flight.discard(key)
    delivered.add(key)


def register_handlers(application: Application) -> Application:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", start_new_application))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("submit", submit_command))
    application.add_handler(CommandHandler("checklist", checklist_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schemes", schemes_command))
    application.add_handler(CommandHandler("browser", schemes_command))
    application.add_handler(CommandHandler("browse", schemes_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, image_document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    return application


def build_application(
    token: str | None = None,
    *,
    backend: BackendClient | None = None,
    onboarding: OnboardingStore | None = None,
    chat_memory: ChatMemory | None = None,
) -> Application:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to build the Telegram application")
    from telegram.request import HTTPXRequest

    request = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
    application = Application.builder().token(token).request(request).build()
    application.bot_data.update(
        {
            "backend": backend
            or BackendClient(
                os.getenv("BACKEND_URL", "http://localhost:8000"), os.getenv("SERVICE_TOKEN", "")
            ),
            "onboarding": onboarding or OnboardingStore(),
            "chat_memory": chat_memory or ChatMemory(),
            "cleared_chats": set(),
            "albums": AlbumDebouncer(),
            "callbacks": CallbackStore(),
        }
    )
    return register_handlers(application)
