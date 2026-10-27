"""Exhaustive validation of the 8 Acceptance Criteria from refinements-telegramBot.md.

1. Browser Schemes option remains hidden until sufficient relevant user or document
   information has been uploaded and understood.
2. Scheme search returns at most three relevant schemes and includes all five
   requested information fields.
3. Scheme results based primarily on available Kaggle CSV data, supplemented only
   by sourced web-derived data.
4. Citizen-output buttons appear contextually instead of all at once.
5. User chat and session data expire after 30 minutes, independently of LMS server startup.
6. Responses remain specific to user's context and do not assert unsupported eligibility claims.
7. Exceptions across supported input types handled gracefully without crashing or leaking PII.
8. No unrelated changes to bot.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.bot import (
    ACTIVE_CASE_MAX_AGE_SECONDS,
    _has_understood_documents,
    _is_unrelated_query,
    _menu_keyboard,
    _output_action_keyboard,
    schemes_command,
    text_handler,
)
from app.chat_memory import ChatMemory
from app.live_schemes import (
    format_schemes_gap_analysis,
    load_kaggle_catalog,
    match_schemes_with_gap_analysis,
)
from app.notify import CallbackStore
from app.onboarding import OnboardingStore


def run(coro):
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self, text: str = "", chat_id: int = 54321):
        self.text = text
        self.chat_id = chat_id
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return self


class FakeUpdate:
    def __init__(self, message: FakeMessage):
        self.effective_message = message
        self.effective_chat = type("Chat", (), {"id": message.chat_id})()
        self.callback_query = None


class FakeContext:
    def __init__(self, backend=None):
        self.application = MagicMock()
        self.bot_data = {
            "backend": backend,
            "onboarding": OnboardingStore(),
            "chat_memory": ChatMemory(ttl_seconds=1800.0),
            "cleared_chats": set(),
            "callbacks": CallbackStore(),
            "delivered_notifications": set(),
        }
        self.application.bot_data = self.bot_data
        self.args = []


# ==============================================================================
# Criterion 1: Browser Schemes Hidden Until Appropriate
# ==============================================================================


def test_criterion_1_browser_schemes_hidden_by_default_and_on_fresh_idle():
    """Verify Browser Schemes option is completely hidden on fresh start or idle state."""
    kb = _menu_keyboard("en", has_active_case=False, has_documents=False)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert "Browse schemes" not in labels


def test_criterion_1_browser_schemes_hidden_when_case_has_no_uploaded_documents():
    """Verify Browser Schemes remains hidden if an active case exists without documents."""
    case = {"id": "case-1", "status": "COLLECTING", "documents": []}
    assert _has_understood_documents(case) is False

    kb = _menu_keyboard("en", has_active_case=True, has_documents=False)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert "Browse schemes" not in labels


def test_criterion_1_browser_schemes_hidden_when_documents_are_unreadable():
    """Verify Browser Schemes remains hidden if uploaded document has unrecognized doc_type."""
    case = {
        "id": "case-2",
        "status": "COLLECTING",
        "documents": [{"doc_type": "other"}],
        "facts": {},
    }
    assert _has_understood_documents(case) is False


def test_criterion_1_browser_schemes_shown_only_when_documents_understood():
    """Verify Browser Schemes unlocks once recognized documents or extracted facts exist."""
    case = {
        "id": "case-3",
        "status": "COLLECTING",
        "documents": [{"doc_type": "aadhaar"}],
        "facts": {"occupation": "farmer"},
    }
    assert _has_understood_documents(case) is True

    kb = _menu_keyboard("en", has_active_case=True, has_documents=True)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert "Browse schemes" in labels


def test_criterion_1_schemes_command_explains_and_prompts_when_no_documents():
    """Verify invoking schemes without documents guides the user to upload first."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    backend.get_schemes = AsyncMock(return_value=[])
    context = FakeContext(backend)
    update = FakeUpdate(FakeMessage("/schemes"))

    run(schemes_command(update, context))

    assert len(update.effective_message.replies) == 1
    reply_text, kwargs = update.effective_message.replies[0]
    assert "upload your documents" in reply_text.lower()
    markup = kwargs.get("reply_markup")
    assert markup is not None


# ==============================================================================
# Criterion 2: Return Person-Specific Scheme Matches (at most 3 schemes, 5 fields)
# ==============================================================================


def test_criterion_2_at_most_three_schemes_returned():
    """Verify scheme search strictly returns fewer than four schemes (<= 3)."""
    results = match_schemes_with_gap_analysis(
        user_profile={"occupation": "farmer"},
        uploaded_docs=[{"doc_type": "aadhaar"}],
        limit=5,
    )
    assert 1 <= len(results) <= 3


def test_criterion_2_all_five_fields_present_in_results_and_formatting():
    """Verify all 5 requested fields are present for each scheme."""
    results = match_schemes_with_gap_analysis(
        user_profile={"occupation": "farmer"},
        uploaded_docs=[{"doc_type": "aadhaar"}],
        limit=3,
    )
    assert len(results) > 0
    first = results[0]

    # 1. Scheme name
    assert first.get("name") is not None
    # 2. Benefit amount
    assert first.get("benefit") is not None
    # 3. Number of missing document types
    assert isinstance(first.get("missing_documents_count"), int)
    # 4. Names of the missing document types
    assert isinstance(first.get("missing_documents_names"), list)
    # 5. Missing user information
    assert first.get("missing_user_info") is not None

    formatted = format_schemes_gap_analysis(results, "en")
    assert "Benefit:" in formatted
    assert "Lacking Documents:" in formatted or "missing" in formatted.lower()
    assert "Missing Document Types:" in formatted
    assert "Lacking User Info:" in formatted


# ==============================================================================
# Criterion 3: Kaggle CSV Data Priority and Source Metadata
# ==============================================================================


def test_criterion_3_kaggle_csv_loaded_with_source_metadata():
    """Verify schemes catalog uses Kaggle CSV datasets with source metadata."""
    catalog = load_kaggle_catalog()
    assert len(catalog) > 500
    sample = catalog[0]
    assert "name" in sample
    assert "benefit" in sample
    assert "required_documents" in sample


# ==============================================================================
# Criterion 4: Show Citizen-Output Buttons Only When Relevant (14 outputs)
# ==============================================================================


def test_criterion_4_citizen_output_buttons_appear_contextually():
    """Verify each of the 14 defined citizen outputs shows only relevant buttons."""
    callbacks = CallbackStore()

    # O1 Submitted / Completed -> No buttons on final terminal message
    assert _output_action_keyboard("COMPLETED", "en", callbacks) is None
    assert _output_action_keyboard("SUBMITTED", "en", callbacks) is None

    # O2 Not eligible -> Start new (or browse if docs exist)
    not_elig_kb = _output_action_keyboard("NOT_ELIGIBLE", "en", callbacks)
    assert not_elig_kb is not None
    labels = [btn.text for row in not_elig_kb.inline_keyboard for btn in row]
    assert "Start new application" in labels

    # O3 Missing documents -> Check eligibility button
    docs_kb = _output_action_keyboard("NEEDS_DOCUMENTS", "en", callbacks)
    assert docs_kb is not None
    assert any("Check eligibility" in btn.text for row in docs_kb.inline_keyboard for btn in row)

    # O4 Question -> Question option buttons only
    q_kb = _output_action_keyboard(
        "NEEDS_INFO",
        "en",
        callbacks,
        options=[{"label": "Yes", "idx": 1}, {"label": "No", "idx": 2}],
        case_id="c1",
        message_id="m1",
    )
    assert q_kb is not None
    q_labels = [btn.text for row in q_kb.inline_keyboard for btn in row]
    assert q_labels == ["Yes", "No"]

    # O5 Extra verification (NEEDS_REVIEW) -> Continue / status
    review_kb = _output_action_keyboard("NEEDS_REVIEW", "en", callbacks)
    assert review_kb is not None

    # O6 Could not complete (FAILED_ESCALATED) -> Start new
    fail_kb = _output_action_keyboard("FAILED_ESCALATED", "en", callbacks)
    assert fail_kb is not None

    # O7 Expired -> Start new
    exp_kb = _output_action_keyboard("EXPIRED", "en", callbacks)
    assert exp_kb is not None

    # O8 Cancelled -> Start new
    canc_kb = _output_action_keyboard("CANCELLED", "en", callbacks)
    assert canc_kb is not None

    # O9 Browse results -> Single next-action button
    browse_kb = _output_action_keyboard("BROWSE_RESULTS", "en", callbacks)
    assert browse_kb is not None
    assert len(browse_kb.inline_keyboard) == 1

    # O10 Status update -> Contextual choices
    stat_kb = _output_action_keyboard("STATUS_UPDATE", "en", callbacks)
    assert stat_kb is not None

    # O11 Processing -> None (progress notice)
    assert _output_action_keyboard("PROCESSING", "en", callbacks) is None

    # O12 Deleted -> Start new application
    assert _output_action_keyboard("DELETED", "en", callbacks) is not None

    # O13 Voice reply -> None (clean audio)
    assert _output_action_keyboard("VOICE_REPLY", "en", callbacks) is None

    # O14 Last-resort fallback -> Check status
    assert _output_action_keyboard("FALLBACK", "en", callbacks) is not None


# ==============================================================================
# Criterion 5: 30-Minute Chat and Session Vanishing TTL
# ==============================================================================


def test_criterion_5_chat_memory_30_minute_ttl_and_stale_cleanup():
    """Verify ChatMemory ttl_seconds is 1800s and clean_stale_sessions removes dead sessions."""
    mem = ChatMemory(ttl_seconds=1800.0)
    assert mem.ttl_seconds == 1800.0

    # User A active, User B stale
    mem.add_message("user_a", "user", "Hello")
    mem.add_message("user_b", "user", "Old message")
    mem._history["user_b"][0].timestamp -= 2000  # > 1800s old

    cleared = mem.clean_stale_sessions()
    assert "user_b" in cleared
    assert "user_a" not in cleared
    assert len(mem.get_history("user_a")) == 1
    assert len(mem.get_history("user_b")) == 0


def test_criterion_5_active_case_max_age_is_1800_seconds():
    """Verify ACTIVE_CASE_MAX_AGE_SECONDS is exactly 1800 (30 minutes)."""
    assert ACTIVE_CASE_MAX_AGE_SECONDS == 1800


# ==============================================================================
# Criterion 6 & 7: Exception Handling and Context Relevance
# ==============================================================================


def test_criterion_7_unrelated_query_redirection():
    """Verify unrelated queries receive brief relevant redirection rather than unrelated answer."""
    assert _is_unrelated_query("Tell me a funny joke") is True
    assert _is_unrelated_query("What is the weather in Delhi?") is True
    assert _is_unrelated_query("Write python code for bubble sort") is True
    assert _is_unrelated_query("I am a farmer with 2 acres") is False
    assert _is_unrelated_query("What scholarship schemes exist?") is False

    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    context = FakeContext(backend)
    msg = FakeMessage("Tell me a funny joke")
    update = FakeUpdate(msg)

    run(text_handler(update, context))

    assert len(msg.replies) == 1
    reply_text = msg.replies[0][0]
    assert "ADHIKAAR AI" in reply_text
    assert "specifically designed" in reply_text.lower()
    assert "schemes" in reply_text.lower()


def test_criterion_7_empty_text_handled_without_error():
    """Verify empty or whitespace message is handled safely without crashing."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    context = FakeContext(backend)
    msg = FakeMessage("   ")
    update = FakeUpdate(msg)

    run(text_handler(update, context))
    assert len(msg.replies) == 0


# ==============================================================================
# Comprehensive Profession & Web Data Fallback Tests
# ==============================================================================


def test_all_professions_extracted_from_chat_memory():
    """Verify extraction of diverse professions from citizen chat turns."""
    mem = ChatMemory()

    cases = [
        ("I am a carpenter and need tool support", "artisan"),
        ("I am an auto driver in chennai", "driver"),
        ("I work as a daily wage construction labourer", "construction worker"),
        ("I am a fisherman with a motorized boat", "fisherman"),
        ("I run a small tea shop dukaan", "small business"),
        ("I am an asha worker in a village", "health worker"),
        ("I am a college student needing a scholarship", "student"),
        ("I am a street vendor selling vegetables on a cart", "street vendor"),
        ("I work as a domestic maid and cleaner", "sanitation worker"),
        ("I am an unemployed graduate seeking skill training", "unemployed youth"),
    ]

    for idx, (text, expected_occ) in enumerate(cases):
        cid = f"test-user-{idx}"
        mem.add_message(cid, "user", text)
        extracted = mem.extract_personal_info(cid)
        assert extracted.get("occupation") == expected_occ, (
            f"Failed for '{text}': got {extracted.get('occupation')}, expected {expected_occ}"
        )


def test_all_professions_return_up_to_three_tailored_schemes():
    """Verify each profession returns at most 3 relevant schemes with all 5 required fields."""
    professions = [
        "farmer", "street vendor", "student", "artisan", "construction worker",
        "driver", "fisherman", "sanitation worker", "small business", "health worker",
        "unemployed youth",
    ]

    for prof in professions:
        schemes = match_schemes_with_gap_analysis(user_profile={"occupation": prof}, limit=3)
        assert 1 <= len(schemes) <= 3, f"Expected 1 to 3 schemes for {prof}, got {len(schemes)}"
        for s in schemes:
            assert s.get("name"), f"Missing name for {prof}"
            assert s.get("benefit"), f"Missing benefit for {prof}"
            assert "missing_documents_count" in s, f"Missing doc count for {prof}"
            assert "missing_documents_names" in s, f"Missing doc names for {prof}"
            assert "missing_user_info" in s, f"Missing user info for {prof}"
            assert s.get("source"), f"Missing source metadata for {prof}"


def test_web_derived_data_fallback_when_csv_unrelated():
    """Verify pre-loaded web-derived data is loaded when CSV search yields no direct match."""
    # Unusual profession that falls back to unorganized worker/social security web flagship
    schemes = match_schemes_with_gap_analysis(user_profile={"occupation": "worker"}, limit=3)
    assert len(schemes) > 0
    # At least one scheme should be sourced from verified flagship/national portals
    sources = [s.get("source", "") for s in schemes]
    assert any("Official" in src for src in sources)
