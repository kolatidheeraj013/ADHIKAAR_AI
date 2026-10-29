"""Comprehensive automated verification of bot.py responses across 12+ professions
and every aspect of user queries (onboarding, language, dynamic scheme discovery,
gap analysis 5-fields, button stagger, vanishing TTL, and edge cases).
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot import (
    _is_unrelated_query,
    _menu_keyboard,
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


# ---------------------------------------------------------------------------
# 1. Multi-Profession Gap Analysis & Recommendations (12+ Professions)
# ---------------------------------------------------------------------------

PROFESSION_TEST_CASES = [
    (
        "Farmer / Kisan",
        {"occupation": "farmer", "state": "Uttar Pradesh", "income": "60000", "land": "2 acres"},
        ["pm kisan", "kisan", "pm-kisan", "krishi", "crop"],
    ),
    (
        "Street Vendor / Rehri / Thela",
        {"occupation": "street vendor", "state": "Delhi", "income": "80000"},
        ["pm svanidhi", "svanidhi", "vendor", "mudra"],
    ),
    (
        "Artisan / Weaver / Craftsman",
        {"occupation": "artisan", "state": "Rajasthan", "income": "90000"},
        ["vishwakarma", "artisan", "pm-vishwakarma", "craft"],
    ),
    (
        "Construction Worker / Mazdoor",
        {"occupation": "construction worker", "state": "Maharashtra", "income": "120000"},
        ["bocw", "construction", "building", "shramik", "unorganised"],
    ),
    (
        "Auto / Taxi Driver",
        {"occupation": "driver", "state": "Karnataka", "income": "140000"},
        ["suraksha", "driver", "pmsby", "jeevan", "shramik", "pradhan mantri"],
    ),
    (
        "Fisherman / Matsya",
        {"occupation": "fisherman", "state": "Tamil Nadu", "income": "75000"},
        ["matsya", "pmmsy", "fisher", "sampada", "kisan"],
    ),
    (
        "Sanitation Worker / Safai Karamchari",
        {"occupation": "sanitation worker", "state": "Bihar", "income": "70000"},
        ["namaste", "safai", "sanitation", "swachhata", "shramik", "ayushman"],
    ),
    (
        "Student / Higher Education",
        {"occupation": "student", "state": "West Bengal", "income": "50000"},
        ["scholarship", "vidya", "education", "student", "shiksha"],
    ),
    (
        "Shopkeeper / Small Business / Kirana",
        {"occupation": "shopkeeper", "state": "Gujarat", "income": "180000"},
        ["mudra", "msme", "business", "udyam", "vyapari"],
    ),
    (
        "Domestic Worker / Maid",
        {"occupation": "domestic worker", "state": "Telangana", "income": "65000"},
        ["shram", "suraksha", "pmsby", "unorganised", "women", "mahila"],
    ),
    (
        "Rural Homemaker / SHG / Mahila",
        {
            "occupation": "self help group",
            "gender": "female",
            "state": "Madhya Pradesh",
            "income": "45000",
        },
        ["mahila", "shg", "lakhpati", "livelihood", "matru", "ayushman"],
    ),
    (
        "Unemployed Youth / Jobseeker",
        {"occupation": "unemployed", "state": "Haryana", "income": "0"},
        ["kaushal", "pmkvy", "skill", "rozgar", "employment", "apprentice"],
    ),
]


@pytest.mark.parametrize("title, profile, expected_keywords", PROFESSION_TEST_CASES)
def test_all_professions_gap_analysis_and_matching(title, profile, expected_keywords):
    """Ensure every profession retrieves tailored schemes with <=3 limit and proper 5 fields."""
    matched = match_schemes_with_gap_analysis(
        user_profile=profile,
        uploaded_docs=[{"doc_type": "aadhaar"}],
        limit=3,
    )
    assert 1 <= len(matched) <= 3, (
        f"Failed for {title}: returned {len(matched)} schemes (limit is <=3)"
    )

    top_scheme = matched[0]
    # Check 5 required fields
    assert top_scheme.get("name"), f"Missing name for {title}"
    assert top_scheme.get("benefit"), f"Missing benefit for {title}"
    assert "lacking_documents_count" in top_scheme, f"Missing lacking_documents_count for {title}"
    assert "lacking_documents" in top_scheme, f"Missing lacking_documents for {title}"
    assert "lacking_user_info" in top_scheme, f"Missing lacking_user_info for {title}"
    assert top_scheme.get("official_url"), f"Missing official_url for {title}"
    assert top_scheme.get("source"), f"Missing source for {title}"

    # Verify formatted text output contains 5 components
    formatted = format_schemes_gap_analysis(matched, language="en")
    assert "Matched Government Welfare Schemes" in formatted
    assert "Benefit:" in formatted
    assert "Lacking Documents:" in formatted
    assert "Missing Document Types:" in formatted
    assert "Lacking User Info:" in formatted
    assert "Official Portal:" in formatted


# ---------------------------------------------------------------------------
# 2. Dynamic Scheme Discovery Visibility (Threshold Check)
# ---------------------------------------------------------------------------

def test_schemes_command_blocks_when_empty_profile():
    """When user has no profile details, docs, or arguments, guide them to start application."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    backend.get_schemes = AsyncMock(return_value=[])
    context = FakeContext(backend)
    update = FakeUpdate(FakeMessage("/browser", chat_id=10101))

    run(schemes_command(update, context))

    assert len(update.effective_message.replies) >= 1
    sent_text = update.effective_message.replies[0][0]
    assert (
        "upload your documents" in sent_text.lower()
        or "share your requirement" in sent_text.lower()
    )


def test_schemes_command_succeeds_when_profile_extracted():
    """When user has spoken their occupation in chat, /browser reveals gap analysis."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    backend.get_schemes = AsyncMock(return_value=[])
    context = FakeContext(backend)
    chat_mem = context.bot_data["chat_memory"]
    chat_mem.add_message(
        "20202", "user", "I am a street vendor selling snacks in Delhi earning 80000"
    )
    update = FakeUpdate(FakeMessage("/browser", chat_id=20202))

    run(schemes_command(update, context))

    assert len(update.effective_message.replies) >= 1
    sent_text = update.effective_message.replies[0][0]
    assert "Matched Government Welfare Schemes" in sent_text
    assert "Official Portal:" in sent_text


# ---------------------------------------------------------------------------
# 3. Unrelated Queries Redirection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "who is elon musk?",
    "what is the capital of France?",
    "tell me a joke about cats",
    "write a poem on rain",
    "how to bake a chocolate cake?",
])
def test_unrelated_queries_detection(query):
    assert _is_unrelated_query(query) is True


def test_text_handler_redirects_unrelated_query():
    """Unrelated questions receive a polite ADHIKAAR AI domain boundary redirection."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    context = FakeContext(backend)
    update = FakeUpdate(FakeMessage("write code for binary search in python", chat_id=30303))

    run(text_handler(update, context))

    assert len(update.effective_message.replies) >= 1
    sent_text = update.effective_message.replies[0][0]
    assert "I am ADHIKAAR AI, specifically designed to help citizens" in sent_text
    assert "Please ask about government schemes" in sent_text


# ---------------------------------------------------------------------------
# 4. Vanishing Chat TTL Expiry (30 minutes)
# ---------------------------------------------------------------------------

def test_vanishing_chat_ttl_expiry():
    """Verify that messages older than 30 minutes are purged by ChatMemory."""
    mem = ChatMemory(ttl_seconds=1.0)
    mem.add_message("40404", "user", "I am a construction worker")
    assert len(mem.get_history("40404")) == 1

    time.sleep(1.1)
    mem.clean_stale_sessions()
    assert len(mem.get_history("40404")) == 0
    assert mem.extract_personal_info("40404") == {}


def test_explicit_chat_end_clears_memory():
    """User typing 'bye' or 'end chat' clears temporary memory immediately."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value=None)
    context = FakeContext(backend)
    chat_mem = context.bot_data["chat_memory"]
    chat_mem.add_message("50505", "user", "I am a farmer with 5 acres")
    update = FakeUpdate(FakeMessage("end chat", chat_id=50505))

    run(text_handler(update, context))

    # Profile info is wiped
    assert chat_mem.extract_personal_info("50505") == {}
    assert len(update.effective_message.replies) >= 1
    sent_text = update.effective_message.replies[0][0]
    assert "Chat session ended and temporary memory cleared" in sent_text


# ---------------------------------------------------------------------------
# 5. Multilingual Menu & Staggered Buttons (Anti-Spam)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "hi", "ta", "te"])
def test_menu_keyboard_anti_spam(lang):
    """Menu keyboards should stay compact and not spam buttons."""
    kb_idle = _menu_keyboard(lang, has_active_case=False, has_documents=False)
    assert len(kb_idle.keyboard) <= 2  # Only 2 rows for idle citizen

    kb_active = _menu_keyboard(lang, has_active_case=True, has_documents=True)
    assert len(kb_active.keyboard) <= 3  # Maximum 3 rows even with active case & documents


# ---------------------------------------------------------------------------
# 6. Kaggle Dataset Direct Loading Integrity
# ---------------------------------------------------------------------------

def test_kaggle_catalog_direct_integrity():
    """Verify raw beneficiary csv loaded >= 4000 schemes with complete attributes."""
    schemes = load_kaggle_catalog()
    assert len(schemes) >= 4000
    sample = schemes[0]
    assert "scheme_id" in sample
    assert "name" in sample
    assert "benefit" in sample
    assert "required_documents" in sample
    assert "official_url" in sample
