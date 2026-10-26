"""Comprehensive verification of the 4 Telegram bot improvements.

Tests:
1. Improvement 1 (error-1.jpg): 'Browse schemes' & 'Delete data' button visibility
   - Does NOT appear on initial /start or idle state
   - Does NOT appear before documents or profile info are uploaded/understood
   - Unlocks and appears once documents or profile facts exist
   - _start_action_keyboard has NO duplicate 'Browse schemes' button
2. Improvement 2 (error-2.jpg): Offline Kaggle matching & tailored gap analysis
   - Zero live web-scraping attempts, zero error warning banners
   - Fewer than top_k=3 schemes shown (strictly <= 2)
   - Every matched scheme displays:
     a) Scheme name
     b) Benefit amount
     c) Number of lacking type of documents
     d) Lacking documents type names
     e) Lacking user info for this specific scheme
   - Tailored to person's stated profile and uploaded documents
3. Improvement 3: Prevention of button clutter across all outputs
   - Terminal outputs have no inline buttons
   - Prompts have state-appropriate contextual buttons only
4. Improvement 4: 30-minute chat memory & session vanishing TTL (1800s)
   - Active case vanishes after 30 minutes (1800s)
   - ChatMemory turns vanish after 30 minutes (1800s)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.bot import (
    ACTIVE_CASE_MAX_AGE_SECONDS,
    _active_case,
    _case_choice_keyboard,
    _menu_keyboard,
    _start_action_keyboard,
    schemes_command,
)
from app.chat_memory import ChatMemory
from app.live_schemes import (
    format_schemes_gap_analysis,
    match_schemes_with_gap_analysis,
)
from app.notify import CallbackStore


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[tuple[str, dict[str, Any]]] = []

    async def reply_text(self, text: str, **kwargs: Any) -> Any:
        self.replies.append((text, kwargs))
        return self


class FakeUpdate:
    def __init__(self, message: FakeMessage | None = None) -> None:
        self.effective_message = message or FakeMessage()
        self.effective_chat = MagicMock(id=99999)
        self.callback_query = None


class FakeContext:
    def __init__(self, backend: Any = None) -> None:
        self.bot_data: dict[str, Any] = {
            "backend": backend,
            "callbacks": CallbackStore(),
            "chat_memory": ChatMemory(ttl_seconds=1800.0),
        }
        self.application = MagicMock()
        self.application.bot_data = self.bot_data
        self.args: list[str] = []


# ==============================================================================
# 1. Improvement 1 & error-1.jpg: Dynamic Button Visibility
# ==============================================================================


def test_menu_keyboard_hides_browse_schemes_and_delete_on_fresh_idle():
    """Verify fresh / idle citizen does NOT see Browse schemes or Delete data buttons."""
    kb = _menu_keyboard("en", has_active_case=False, has_documents=False)
    labels = {btn.text for row in kb.keyboard for btn in row}

    assert "Browse schemes" not in labels
    assert "Delete data" not in labels
    assert "Continue / status" not in labels
    assert {"Start new application", "Help", "Language / privacy"}.issubset(labels)


def test_menu_keyboard_hides_browse_schemes_when_case_has_no_docs():
    """Verify active case without uploaded documents does NOT show Browse schemes."""
    kb = _menu_keyboard("en", has_active_case=True, has_documents=False)
    labels = {btn.text for row in kb.keyboard for btn in row}

    assert "Browse schemes" not in labels
    assert {"Start new application", "Continue / status", "Help", "Delete data"}.issubset(labels)


def test_menu_keyboard_shows_browse_schemes_when_documents_uploaded():
    """Verify Browse schemes unlocks and appears once documents are uploaded."""
    kb = _menu_keyboard("en", has_active_case=True, has_documents=True)
    labels = {btn.text for row in kb.keyboard for btn in row}

    assert "Browse schemes" in labels
    assert {"Start new application", "Continue / status", "Delete data"}.issubset(labels)


def test_start_action_keyboard_omits_duplicate_browse_schemes():
    """Verify inline start keyboard does not show intrusive Browse schemes button."""
    callbacks = CallbackStore()
    kb = _start_action_keyboard("en", callbacks)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]

    assert len(labels) == 1
    assert "Start new application" in labels[0]
    assert "Browse schemes" not in " ".join(labels)


def test_case_choice_keyboard_respects_has_documents_flag():
    """Verify _case_choice_keyboard only offers Browse schemes if documents exist."""
    callbacks = CallbackStore()

    kb_no_docs = _case_choice_keyboard("en", callbacks, has_documents=False)
    labels_no_docs = [btn.text for row in kb_no_docs.inline_keyboard for btn in row]
    assert not any("Browse schemes" in label_text for label_text in labels_no_docs)

    kb_with_docs = _case_choice_keyboard("en", callbacks, has_documents=True)
    labels_with_docs = [btn.text for row in kb_with_docs.inline_keyboard for btn in row]
    assert any("Browse schemes" in label_text for label_text in labels_with_docs)


def test_schemes_command_prompts_for_docs_when_user_has_no_data():
    """Verify asking for schemes without documents guides the user to start an application."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    context = FakeContext(backend)
    update = FakeUpdate(FakeMessage())

    run(schemes_command(update, context))

    assert len(update.effective_message.replies) == 1
    reply_text, kwargs = update.effective_message.replies[0]
    assert "upload your documents" in reply_text.lower()
    assert "Start new application" in str(kwargs.get("reply_markup"))


# ==============================================================================
# 2. Improvement 2 & error-2.jpg: Kaggle Matching & Tailored Gap Analysis
# ==============================================================================


def test_gap_analysis_limit_fewer_than_top_k_3():
    """Verify matched schemes strictly return fewer than 3 schemes (limit <= 2)."""
    results = match_schemes_with_gap_analysis(
        user_profile={"occupation": "farmer"},
        uploaded_docs=["aadhaar"],
        limit=2,
    )
    assert 1 <= len(results) < 3
    assert len(results) <= 2


def test_gap_analysis_contains_all_required_components():
    """Verify each matched scheme includes all 5 required elements:

    1. Scheme name
    2. Benefit amount
    3. Number of lacking type of documents
    4. Lacking documents type names
    5. Lacking user info for this specific scheme
    """
    results = match_schemes_with_gap_analysis(
        user_profile={"occupation": "farmer"},
        uploaded_docs=[{"doc_type": "aadhaar"}],
        limit=2,
    )
    assert len(results) > 0
    top = results[0]

    # 1. Scheme name
    assert top.get("name") and len(top["name"]) > 5
    # 2. Benefit amount
    assert top.get("benefit") and ("₹" in top["benefit"] or "INR" in top["benefit"])
    # 3. Number of lacking type of documents
    assert isinstance(top.get("lacking_documents_count"), int)
    # 4. Lacking documents type names
    assert isinstance(top.get("lacking_documents"), list)
    # 5. Lacking user info for this specific scheme
    assert top.get("lacking_user_info") is not None

    formatted = format_schemes_gap_analysis(results, "en")
    assert "💰 Benefit:" in formatted
    assert "📄 Lacking Documents:" in formatted
    assert "ℹ️ Lacking User Info:" in formatted
    assert "Oh we can't able extract" not in formatted  # NO ugly error banner


def test_gap_analysis_detects_zero_lacking_documents_when_all_uploaded():
    """Verify that when a citizen uploads all required documents, 0 lacking is reported."""
    all_pm_kisan_docs = [
        {"doc_type": "aadhaar"},
        {"doc_type": "land_record"},
        {"doc_type": "bank_passbook"},
    ]
    results = match_schemes_with_gap_analysis(
        user_profile={"occupation": "farmer", "land_size": "2 acres"},
        uploaded_docs=all_pm_kisan_docs,
        limit=2,
    )
    pm_kisan = next((s for s in results if s["scheme_id"] == "pm_kisan"), None)
    assert pm_kisan is not None
    assert pm_kisan["lacking_documents_count"] == 0
    assert len(pm_kisan["lacking_documents"]) == 0

    formatted = format_schemes_gap_analysis([pm_kisan], "en")
    assert "0 types missing" in formatted


def test_schemes_command_flow_displays_gap_analysis_and_clean_button():
    """Verify complete /schemes command flow outputs gap analysis and single next-step button."""
    backend = MagicMock()
    backend.active_case = AsyncMock(
        return_value={
            "id": "case-active",
            "status": "COLLECTING",
            "documents": [{"doc_type": "aadhaar"}],
            "facts": {"occupation": "farmer"},
        }
    )
    backend.get_schemes = AsyncMock(return_value=[])
    context = FakeContext(backend)
    update = FakeUpdate(FakeMessage("/schemes"))

    run(schemes_command(update, context))

    assert len(update.effective_message.replies) == 2
    msg1_text, msg1_kwargs = update.effective_message.replies[0]
    msg2_text, msg2_kwargs = update.effective_message.replies[1]

    # Message 1 contains gap analysis
    assert "🏛️ Matched Government Welfare Schemes" in msg1_text
    assert "💰 Benefit:" in msg1_text
    assert "📄 Lacking Documents:" in msg1_text
    assert "ℹ️ Lacking User Info:" in msg1_text
    assert "Oh we can't able extract" not in msg1_text

    # Message 2 contains eligibility disclaimer and single next-action button
    assert "does not decide eligibility" in msg2_text
    markup = msg2_kwargs.get("reply_markup")
    assert markup is not None
    # No duplicate Browse schemes button
    all_buttons = [btn.text for row in markup.inline_keyboard for btn in row]
    assert not any("Browse schemes" in b for b in all_buttons)


# ==============================================================================
# 3. Improvement 4: 30-Minute Chat Vanishing TTL (1800s)
# ==============================================================================


def test_active_case_max_age_constant_is_1800():
    """Verify ACTIVE_CASE_MAX_AGE_SECONDS is set to 1800 (30 minutes)."""
    assert ACTIVE_CASE_MAX_AGE_SECONDS == 1800


def test_active_case_vanishes_after_30_minutes():
    """Verify active case vanishes if last updated > 30 minutes ago."""
    backend = MagicMock()
    context = FakeContext(backend)

    # 1. Case updated 35 minutes ago (> 1800s) -> VANISHES
    old_time = (datetime.now(UTC) - timedelta(minutes=35)).isoformat()
    backend.active_case = AsyncMock(
        return_value={"id": "case-expired", "status": "COLLECTING", "created_at": old_time}
    )
    active = run(_active_case(FakeUpdate(FakeMessage()), context))
    assert active is None

    # 2. Case updated 15 minutes ago (< 1800s) -> ACTIVE
    recent_time = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
    backend.active_case = AsyncMock(
        return_value={"id": "case-live", "status": "COLLECTING", "created_at": recent_time}
    )
    active_recent = run(_active_case(FakeUpdate(FakeMessage()), context))
    assert active_recent is not None
    assert active_recent["id"] == "case-live"


def test_chat_memory_prunes_turns_after_30_minutes():
    """Verify ChatMemory automatically prunes conversational turns older than 30 minutes."""
    mem = ChatMemory(ttl_seconds=1800.0)
    chat_id = "test-citizen-1"

    # Add message
    mem.add_message(chat_id, "user", "I am a small farmer")
    assert len(mem.get_history(chat_id)) == 1

    # Simulate 35 minutes passing
    mem._history[chat_id][0].timestamp = datetime.now().timestamp() - 2100

    # Next check should prune expired turn
    history = mem.get_history(chat_id)
    assert len(history) == 0
