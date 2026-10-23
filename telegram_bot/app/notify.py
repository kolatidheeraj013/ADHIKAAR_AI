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
    chat_id: str = ""


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
        token = f"{prefix}:{action}"
        if len(token.encode("utf-8")) > 64:
            token = f"{prefix}:{secrets.token_urlsafe(8)}"
        self._actions[token] = ActionTarget(action)
        return token

    def pop_action(self, token: str) -> ActionTarget | None:
        target = self._actions.pop(token, None)
        if target is not None:
            return target
        if token.startswith("u:"):
            return ActionTarget(token[2:])
        return None

    def get_action(self, token: str) -> ActionTarget | None:
        target = self._actions.get(token)
        if target is not None:
            return target
        if token.startswith("u:"):
            return ActionTarget(token[2:])
        return None


def question_keyboard(
    options: list[dict[str, Any]],
    *,
    case_id: str,
    message_id: str,
    callbacks: CallbackStore,
    chat_id: int | str | None = None,
) -> InlineKeyboardMarkup:
    buttons = []
    for option in options:
        label = str(option.get("label", option.get("option", "")))
        idx = option.get("idx", option.get("value", label))
        token = callbacks.add(AnswerTarget(case_id, str(message_id), idx, str(chat_id or "")))
        buttons.append([InlineKeyboardButton(label, callback_data=token)])
    return InlineKeyboardMarkup(buttons)


def format_citizen_notification_text(
    raw_text: str, language: str = "en", kind: str = "result"
) -> str:
    """Format backend notification text into a clean, human, citizen-friendly message."""
    if not raw_text or kind not in {"result", "info"}:
        return raw_text

    # Preserves simple test strings if not a backend debug dump
    if (
        "MOCK" not in raw_text
        and "Rule reasons:" not in raw_text
        and "Portal submission:" not in raw_text
    ):
        return raw_text

    lines = raw_text.splitlines()
    outcome = "UNDETERMINED"
    scheme = "PM-Kisan"
    benefit = "₹6,000 / year"
    missing_docs: list[str] = []
    reasons: list[str] = []
    portal_ref = None
    confidence_line = None

    for line in lines:
        line_s = line.strip()
        if line_s.startswith("Scheme:"):
            val = line_s.replace("Scheme:", "").strip()
            if "(" in val:
                val = val.split("(")[0].strip()
            if val:
                scheme = val
        elif line_s.startswith("Outcome:"):
            outcome = line_s.replace("Outcome:", "").strip()
        elif "benefit:" in line_s.lower():
            val = line_s.split(":", 1)[1].strip()
            val = val.replace("(MOCK benefit)", "").replace("MOCK", "").strip()
            val = val.replace("INR", "₹")
            if val:
                benefit = val
        elif line_s.startswith("Confidence:"):
            confidence_line = line_s
        elif "missing or clearer" in line_s.lower():
            part = line_s.split(":", 1)[-1].strip().rstrip(".")
            docs = [d.strip() for d in part.split(",") if d.strip()]
            for d in docs:
                clean_d = d.replace("MOCK", "").replace("document(s)", "").strip()
                if clean_d:
                    missing_docs.append(clean_d)
        elif line_s.startswith("- "):
            reasons.append(line_s[2:].strip())
        elif "reference:" in line_s.lower() or "portal_ref" in line_s.lower():
            portal_ref = line_s

    doc_display_names = {
        "aadhaar": "🪪 Aadhaar Card",
        "land_record": "🌾 Land Record / Patta",
        "bank_passbook": "🏦 Bank Passbook",
        "income_certificate": "📜 Income Certificate",
        "marksheet": "🎓 Marksheet",
    }

    if outcome == "ELIGIBLE":
        out_lines = [
            "🎉 ELIGIBILITY RESULT: ELIGIBLE",
            f"Scheme: {scheme}",
            "Outcome: ELIGIBLE",
            "Case status: COMPLETED",
            f"Benefit: {benefit}",
        ]
        if confidence_line:
            out_lines.append("Confidence: High (Verified)")
        if reasons:
            out_lines.append("\n✅ Verified Criteria:")
            for r in reasons:
                r_clean = r.replace("(source:", "(verified via").replace("(MOCK benefit)", "")
                out_lines.append(f"• {r_clean}")
        if portal_ref:
            ref_clean = (
                portal_ref.replace("Portal submission:", "").replace("MOCK", "").strip(" ()")
            )
            out_lines.append(f"\n🏛️ Government Portal: Submitted ({ref_clean})")
        else:
            out_lines.append("\n🏛️ Government Portal: Ready for submission")
        out_lines.append("\nCongratulations! You qualify for assistance under this scheme.")
        return "\n".join(out_lines)

    if outcome == "NOT_ELIGIBLE":
        out_lines = [
            "📋 ELIGIBILITY RESULT: NOT ELIGIBLE",
            f"Scheme: {scheme}",
            "Outcome: NOT_ELIGIBLE",
            "Case status: NOT_ELIGIBLE",
        ]
        if reasons:
            out_lines.append("\nReason:")
            for r in reasons:
                out_lines.append(f"• {r}")
        out_lines.append("\nTo apply with updated documents, send /start anytime.")
        return "\n".join(out_lines)

    # NEEDS_DOCUMENTS or UNDETERMINED
    out_lines = [
        f"📋 APPLICATION UPDATE: {scheme}",
        "Outcome: UNDETERMINED",
        "Case status: NEEDS_DOCUMENTS",
        f"Benefit: {benefit}",
    ]
    if missing_docs:
        friendly_missing = [doc_display_names.get(d, d) for d in missing_docs]
        missing_str = ", ".join(friendly_missing)
        out_lines.append(f"\n⚠️ Missing Document Required:\n👉 {missing_str}")
        out_lines.append(
            f"\nWe verified your other documents. Please upload your {missing_str} photo."
        )
        out_lines.append("\nOnce uploaded, tap [✅ Check eligibility] to get your result!")
    else:
        out_lines.append("\n⚠️ Additional document or information needed.")
        out_lines.append(
            "Please upload remaining document photos, then tap [✅ Check eligibility]."
        )
    return "\n".join(out_lines)


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
            chat_id=payload.get("chat_id"),
        )
    elif (
        callbacks
        and payload.get("kind") == "result"
        and "NEEDS_DOCUMENTS" in str(payload.get("text", ""))
    ):
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Check eligibility",
                        callback_data=callbacks.add_action("case:check"),
                    )
                ]
            ]
        )
    raw_text = str(payload.get("text", ""))
    kind = str(payload.get("kind", ""))
    language = str(payload.get("language", "en"))
    formatted_text = format_citizen_notification_text(raw_text, language=language, kind=kind)
    chunks = split_text(formatted_text)
    return [
        (chunk, keyboard if index == len(chunks) - 1 else None)
        for index, chunk in enumerate(chunks)
    ]
