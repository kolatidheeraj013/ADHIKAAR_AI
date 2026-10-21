"""Telegram handlers. This module translates Telegram updates into backend calls."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
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
from .i18n import t
from .notify import AnswerTarget, CallbackStore, render_notification
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


def _menu_keyboard(language: str = "en", *, active_state: str | None = None) -> ReplyKeyboardMarkup:
    if active_state in {"COLLECTING", "NEEDS_DOCUMENTS"}:
        return ReplyKeyboardMarkup(
            [
                [t(language, "menu_done")],
                [t(language, "menu_cancel")],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder=t(language, "menu_placeholder"),
        )
    if active_state in {"PROCESSING", "NEEDS_INFO"}:
        return ReplyKeyboardMarkup(
            [
                [t(language, "menu_cancel")],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="Processing...",
        )
    return ReplyKeyboardMarkup(
        [
            [t(language, "menu_start"), t(language, "menu_continue")],
            [t(language, "menu_schemes"), t(language, "menu_help")],
            [t(language, "menu_delete"), t(language, "menu_language")],
        ],
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
    "NEEDS_REVIEW": "Please wait for a volunteer to review your case.",
    "SUBMITTED": "Please wait for the scheme portal confirmation.",
    "COMPLETED": "No further action is needed.",
    "NOT_ELIGIBLE": "No further action is needed.",
    "FAILED_ESCALATED": "A volunteer will follow up with you.",
}


def _status_text(language: str, case: dict[str, Any]) -> str:
    status = str(case.get("status") or "active")
    messages = case.get("messages") or []
    recent_lines: list[str] = []
    for message in messages[-3:]:
        if not isinstance(message, dict):
            continue
        if message.get("kind") not in {"info", "question", "result"}:
            continue
        text = str(message.get("text") or "").strip()
        if text:
            recent_lines.append(f"• {text[:500]}")
    recent = "\n".join(recent_lines) or t(language, "no_recent_updates")
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


async def _active_case(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    backend: BackendClient = _data(context, "backend")
    if backend is None:
        return None
    return await backend.active_case(_chat_id(update))


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
                    t(language, "menu_done"), callback_data=callbacks.add_action("start:done")
                )
            ]
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


def _case_choice_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
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
    )


def _replace_case_keyboard(language: str, callbacks: CallbackStore) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "replace_confirm"),
                    callback_data=callbacks.add_action("case:replace"),
                ),
                InlineKeyboardButton(
                    t(language, "no"), callback_data=callbacks.add_action("case:cancel")
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


async def _send(
    update: Update,
    text: str,
    *,
    language: str = "en",
    active_state: str | None = None,
    **kwargs: Any,
) -> Any:
    message = update.effective_message
    if message is None:
        return None
    kwargs.setdefault("reply_markup", _menu_keyboard(language, active_state=active_state))
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


async def _edit_callback(query: Any, text: str, **kwargs: Any) -> None:
    try:
        await query.edit_message_text(text, **kwargs)
    except Exception:
        # Callback messages can be stale or already edited. Do not let Telegram
        # API errors turn a user action into an unhandled update exception.
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
        await _send(
            update,
            _status_text(language, active),
            language=language,
            reply_markup=_case_choice_keyboard(language, _callbacks(context)),
        )
        return
    await _begin_onboarding(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        active = await _active_case(update, context)
    except Exception as exc:
        await _send_backend_error(update, _language(update, context), exc, action="status")
        return
    language = _language(update, context, active)
    if not active:
        await _send(update, t(language, "no_active"), language=language)
        return
    await _send(update, _status_text(language, active), language=language)


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
    for idx, d in enumerate(docs, 1):
        dtype = d.get("doc_type", "other")
        label = type_labels.get(dtype, dtype)
        lines.append(f"{idx}. {label}")
    if not docs:
        lines.append("No documents attached yet.")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("Target Scheme: PM-Kisan (MOCK)")
    lines.append(f"👉 Tap [{t(language, 'menu_done')}] to evaluate eligibility.")
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


def _scheme_text(language: str, schemes: list[dict[str, Any]]) -> str:
    lines = [t(language, "schemes_header")]
    for scheme in schemes:
        name = str(scheme.get("name") or scheme.get("scheme_id") or "Unnamed scheme")
        benefit = str(scheme.get("benefit") or t(language, "scheme_benefit_unknown"))
        documents = scheme.get("required_documents") or []
        document_text = ", ".join(str(item) for item in documents) or t(
            language, "scheme_documents_unknown"
        )
        lines.append(
            t(language, "scheme_item", name=name, benefit=benefit, documents=document_text)
        )
    return "\n\n".join(lines)


async def schemes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = _language(update, context)
    backend: BackendClient = _data(context, "backend")
    if backend is None:
        await _send_backend_error(update, language, BackendUnavailableError(), action="schemes")
        return
    try:
        schemes = await backend.get_schemes()
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="schemes")
        return
    if not schemes:
        await _send(update, t(language, "schemes_empty"), language=language)
        return
    await _send(update, _scheme_text(language, schemes), language=language)
    await _send(
        update,
        t(language, "scheme_need_prompt"),
        language=language,
        reply_markup=_start_action_keyboard(language, _callbacks(context)),
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
    action_target = callbacks.pop_action(data)
    action = (
        action_target.action
        if action_target
        else {
            # Keep old callback values readable for messages issued before a bot restart.
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
            "start:done": "start:done",
        }.get(data)
    )
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
    language = onboarding.language_for(chat_id)
    if action in {
        "case:new",
        "case:replace",
        "case:continue",
        "case:cancel",
        "delete:yes",
        "delete:no",
        "start:done",
    }:
        try:
            active_for_language = await _active_case(update, context)
        except Exception:
            active_for_language = None
        if active_for_language and active_for_language.get("language"):
            language = str(active_for_language["language"])
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
        await _edit_callback(
            query,
            t(language, "step_guide"),
            reply_markup=None,
        )
        context.application.bot_data.setdefault("cases", {})[str(chat_id)] = _case_id(case)
        await _send(
            update,
            t(language, "prompt_input", seconds=MAX_VOICE_SECONDS),
            language=language,
            active_state="COLLECTING",
            reply_markup=_done_keyboard(language, callbacks),
        )
        return
    if action and action.startswith("tag:"):
        parts = action.split(":")
        if len(parts) >= 3:
            doc_id, chosen_type = parts[1], parts[2]
            active = await _active_case(update, context)
            if active and backend and doc_id != "pending":
                try:
                    await backend.classify_document(_case_id(active) or "", doc_id, chosen_type)
                except Exception:
                    pass
            tag_label = t(language, f"doc_tag_{chosen_type}")
            await _edit_callback(
                query,
                f"✅ {tag_label} saved!\nSend remaining photos or tap Submit:",
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
            active = await _active_case(update, context)
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
        try:
            active = await _active_case(update, context)
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="status"))
            return
        if active:
            await _edit_callback(query, _status_text(language, active), reply_markup=None)
        else:
            await _edit_callback(query, t(language, "no_active"), reply_markup=None)
        return
    if action == "delete:no":
        await _edit_callback(query, t(language, "delete_cancelled"), reply_markup=None)
        return
    if action == "delete:yes":
        try:
            active = await _active_case(update, context)
            if active and backend:
                await backend.delete_case(_case_id(active) or "")
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="delete"))
            return
        onboarding.clear(chat_id)
        await _edit_callback(query, t(language, "deleted"), reply_markup=None)
        return
    if action == "start:done":
        try:
            active = await _active_case(update, context)
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="start case"))
            return
        if not active or not backend:
            await _edit_callback(query, t(language, "no_active"))
            return
        try:
            await backend.start_case(_case_id(active) or "")
        except Exception as exc:
            await _edit_callback(query, _error_text(language, exc, action="start case"))
            return
        await _edit_callback(query, t(language, "working"), reply_markup=None)
        await _send(
            update,
            (
                "🔍 ADHIKAAR is evaluating your case...\n"
                "Checking document facts and scheme rules. Your outcome will appear momentarily."
            ),
            language=language,
            active_state="PROCESSING",
        )
        return
    if data.startswith("a:"):
        callbacks: CallbackStore = _data(context, "callbacks", CallbackStore())
        target: AnswerTarget | None = callbacks.get(data)
        if target is None or not backend:
            await _edit_callback(query, t(language, "callback_unavailable"))
            return
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


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    text = message.text if message else None
    if text:
        menu_actions = {
            "menu_start": start_new_application,
            "menu_continue": status_command,
            "menu_schemes": schemes_command,
            "menu_help": help_command,
            "menu_delete": delete_command,
            "menu_cancel": delete_command,
            "menu_language": language_command,
            "menu_checklist": checklist_command,
        }
        for language in ("en", "ta", "te", "hi"):
            for key, handler in menu_actions.items():
                if text.strip() == t(language, key):
                    await handler(update, context)
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
        await _send(update, t(language, "not_ready"), language=language)
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
    }
    for lang in ("en", "ta", "te", "hi"):
        done_triggers.add(t(lang, "done").strip().lower())
        done_triggers.add(t(lang, "menu_done").strip().lower())

    if clean_text in done_triggers:
        try:
            await backend.start_case(case_id)
        except Exception as exc:
            await _send_backend_error(update, language, exc, action="start case")
            return
        await _send(update, t(language, "working"), language=language, active_state="PROCESSING")
        await _send(
            update,
            (
                "🔍 ADHIKAAR is evaluating your case...\n"
                "Checking document facts and scheme rules. Your outcome will appear momentarily."
            ),
            language=language,
            active_state="PROCESSING",
        )
        return

    try:
        await backend.send_text(case_id, text)
    except Exception as exc:
        await _send_backend_error(update, language, exc, action="send text")
        return
    await _send(
        update,
        t(language, "received_text"),
        language=language,
        active_state=active.get("status") if active else "COLLECTING",
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
    done_msg = t(language, "menu_done")
    ack_msg = t(language, "received_documents", count=count)
    await _send(
        update,
        (
            f"{ack_msg}\n\n"
            "🔒 Photos secured & encrypted (chat copies removed for DPDP privacy).\n"
            f"👉 Tap [{done_msg}] when ready to evaluate eligibility."
        ),
        language=language,
        active_state=active.get("status") if active else "COLLECTING",
        reply_markup=_done_keyboard(language, callbacks),
    )


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

    caption = (getattr(message, "caption", "") or "").lower()
    doc_type = None
    if any(k in caption for k in ("aadhaar", "adhar", "uid")):
        doc_type = "aadhaar"
    elif any(k in caption for k in ("land", "patta", "chitta", "khasra", "7/12")):
        doc_type = "land_record"
    elif any(k in caption for k in ("bank", "passbook", "account")):
        doc_type = "bank_passbook"
    elif any(k in caption for k in ("income", "aay")):
        doc_type = "income_certificate"
    elif any(k in caption for k in ("marksheet", "mark", "10th", "12th")):
        doc_type = "marksheet"

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
        done_msg = t(language, "menu_done")
        if doc_type:
            tag_label = t(language, f"doc_tag_{doc_type}")
            text = (
                f"{ack_msg}\n\n✅ {tag_label} received.\n"
                "🔒 Chat copy removed for DPDP privacy.\n"
                f"👉 Tap [{done_msg}] to evaluate eligibility."
            )
        else:
            text = (
                f"{ack_msg}\n\n"
                "🔒 Chat copy removed for DPDP privacy.\n"
                f"👉 Tap [{done_msg}] to evaluate eligibility."
            )
        reply_markup = _done_keyboard(language, callbacks)
        await _send(
            update,
            text,
            language=language,
            active_state=active.get("status") if active else "COLLECTING",
            reply_markup=reply_markup,
        )


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
    caption = (getattr(message, "caption", "") or "").lower()
    combined = f"{raw_name.lower()} {caption}"
    doc_type = None
    if any(k in combined for k in ("aadhaar", "adhar", "uid")):
        doc_type = "aadhaar"
    elif any(k in combined for k in ("land", "patta", "chitta", "khasra", "7/12")):
        doc_type = "land_record"
    elif any(k in combined for k in ("bank", "passbook", "account")):
        doc_type = "bank_passbook"
    elif any(k in combined for k in ("income", "aay")):
        doc_type = "income_certificate"
    elif any(k in combined for k in ("marksheet", "mark", "10th", "12th")):
        doc_type = "marksheet"

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
        done_msg = t(language, "menu_done")
        if doc_type:
            tag_label = t(language, f"doc_tag_{doc_type}")
            text = (
                f"{ack_msg}\n\n✅ {tag_label} received.\n"
                "🔒 Chat copy removed for DPDP privacy.\n"
                f"👉 Tap [{done_msg}] to evaluate eligibility."
            )
        else:
            text = (
                f"{ack_msg}\n\n"
                "🔒 Chat copy removed for DPDP privacy.\n"
                f"👉 Tap [{done_msg}] to evaluate eligibility."
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
    for text, keyboard in render_notification(payload, callbacks=callbacks):
        await application.bot.send_message(
            chat_id=payload["chat_id"], text=text, reply_markup=keyboard
        )


def register_handlers(application: Application) -> Application:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", start_new_application))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("checklist", checklist_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("schemes", schemes_command))
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
) -> Application:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required to build the Telegram application")
    application = Application.builder().token(token).build()
    application.bot_data.update(
        {
            "backend": backend
            or BackendClient(
                os.getenv("BACKEND_URL", "http://localhost:8000"), os.getenv("SERVICE_TOKEN", "")
            ),
            "onboarding": onboarding or OnboardingStore(),
            "albums": AlbumDebouncer(),
            "callbacks": CallbackStore(),
        }
    )
    return register_handlers(application)
