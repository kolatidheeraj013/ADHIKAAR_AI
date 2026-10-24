"""Tests for Telegram bot refinements.

Covers: Kaggle scheme browser, chat memory, volunteer removal, active case expiry,
and outcome delivery.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot import (
    _NEXT_ACTIONS,
    _active_case,
    text_handler,
)
from app.chat_memory import ChatMemory
from app.live_schemes import (
    LIVE_EXTRACTION_FAILURE_MSG,
    fetch_live_government_schemes,
    load_kaggle_catalog,
    search_kaggle_schemes,
)
from app.notify import CallbackStore
from app.onboarding import OnboardingStore


def run(coro):
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self, text: str | None = None, chat_id: int = 12345, photo=None):
        self.text = text
        self.chat_id = chat_id
        self.photo = photo
        self.replies: list[tuple[str, dict]] = []
        self.deleted = False

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return self

    async def delete(self):
        self.deleted = True


class FakeUpdate:
    def __init__(self, message: FakeMessage):
        self.effective_message = message
        self.message = message
        self.effective_chat = type("Chat", (), {"id": message.chat_id})()


class FakeContext:
    def __init__(self, backend=None):
        self.application = MagicMock()
        self.bot_data = {
            "backend": backend,
            "onboarding": OnboardingStore(),
            "chat_memory": ChatMemory(),
            "cleared_chats": set(),
            "callbacks": CallbackStore(),
            "delivered_notifications": set(),
        }
        self.application.bot_data = self.bot_data
        self.args = []


def test_kaggle_catalog_loads_primary_myscheme_and_backup_indgov():
    """Verify Kaggle schemes catalog loader reads primary myscheme.gov and backup."""
    catalog = load_kaggle_catalog()
    assert len(catalog) > 100
    # Core schemes must exist with verified fields
    pm_kisan = next((s for s in catalog if s["scheme_id"] == "pm_kisan"), None)
    assert pm_kisan is not None
    assert "₹6,000" in pm_kisan["benefit"]
    assert len(pm_kisan["required_documents"]) >= 2
    assert "official_url" in pm_kisan
    assert "ministry" in pm_kisan


def test_search_kaggle_schemes_by_farmer_keyword():
    """Verify keyword searching in Kaggle catalog finds relevant welfare schemes."""
    farmer_schemes = search_kaggle_schemes(query="farmer", limit=4)
    assert len(farmer_schemes) >= 1
    names = " ".join(
        s["name"].lower() + " " + s.get("categories", "").lower() for s in farmer_schemes
    )
    assert any(w in names for w in ("kisan", "farmer", "agriculture"))


def test_live_schemes_fallback_uses_kaggle_catalog_when_extraction_fails():
    """Verify fetch_live_government_schemes returns Kaggle dataset with failure notice."""
    with patch("httpx.AsyncClient.get", side_effect=Exception("Blocked by live website")):
        schemes, notice = run(fetch_live_government_schemes(timeout=0.1))
        assert notice == LIVE_EXTRACTION_FAILURE_MSG
        assert len(schemes) >= 6
        assert any("kisan" in s["name"].lower() for s in schemes)


def test_no_volunteer_references_in_outcome_or_status():
    """Verify volunteer action is removed completely from next action strings."""
    assert "volunteer" not in _NEXT_ACTIONS["NEEDS_REVIEW"].lower()
    assert "volunteer" not in _NEXT_ACTIONS["FAILED_ESCALATED"].lower()
    assert "official verification" in _NEXT_ACTIONS["NEEDS_REVIEW"].lower()
    assert "official" in _NEXT_ACTIONS["FAILED_ESCALATED"].lower()


def test_temporary_chat_memory_records_and_extracts_personal_info():
    """Verify ChatMemory records rolling conversation turns and extracts facts."""
    mem = ChatMemory(max_turns=6, ttl_seconds=3600)
    chat_id = "citizen-99"

    mem.add_message(chat_id, "user", "I am a small farmer with 2 acres of land in Andhra Pradesh")
    mem.add_message(chat_id, "bot", "Understood. Please upload your documents.")

    history = mem.get_history(chat_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert "farmer" in history[0].text

    info = mem.extract_personal_info(chat_id)
    assert info.get("occupation") == "farmer"
    assert "2" in info.get("land_size", "")
    assert info.get("state") == "Andhra Pradesh"

    mem.clear(chat_id)
    assert len(mem.get_history(chat_id)) == 0


def test_text_handler_triggers_browser_on_personal_info_benefits_prompt():
    """Verify prompt 'I need to know the benefits of mine personal info' triggers browser."""
    backend = MagicMock()
    backend.get_schemes = AsyncMock(return_value=[])
    context = FakeContext(backend)

    # Pre-populate temporary chat memory with farmer info
    chat_mem = context.bot_data["chat_memory"]
    chat_mem.add_message("12345", "user", "I am a farmer with 1.5 acres in Tamil Nadu")

    msg = FakeMessage("I need to know the benefits of mine personal info")
    update = FakeUpdate(msg)

    run(text_handler(update, context))

    assert len(msg.replies) >= 1
    reply_text = msg.replies[0][0]
    # Must display welfare schemes and personalized profile note
    assert any(k in reply_text for k in ("Pradhan Mantri", "PM-Kisan", "Welfare Schemes", "farmer"))


def test_active_case_vanishes_after_ending_chat():
    """Verify ending chat clears memory and vanishes active case."""
    backend = MagicMock()
    backend.active_case = AsyncMock(return_value={"id": "case-active", "status": "COLLECTING"})
    context = FakeContext(backend)

    # 1. Before ending chat, active case is returned
    msg_active = FakeMessage("status")
    active_before = run(_active_case(FakeUpdate(msg_active), context))
    assert active_before is not None

    # 2. Citizen ends chat
    msg_end = FakeMessage("end chat")
    run(text_handler(FakeUpdate(msg_end), context))

    assert len(msg_end.replies) >= 1
    assert "ended and temporary memory cleared" in msg_end.replies[0][0]

    # 3. Active case now vanishes (returns None)
    active_after = run(_active_case(FakeUpdate(msg_active), context))
    assert active_after is None


def test_active_case_vanishes_when_expired_or_terminal():
    """Verify active case vanishes if expired (>1 hour) or reached terminal status."""
    backend = MagicMock()
    context = FakeContext(backend)

    # Terminal case: COMPLETED
    backend.active_case = AsyncMock(return_value={"id": "case-done", "status": "COMPLETED"})
    res = run(_active_case(FakeUpdate(FakeMessage()), context))
    assert res is None

    # Expired case: created 2 hours ago
    old_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    backend.active_case = AsyncMock(
        return_value={"id": "case-old", "status": "COLLECTING", "created_at": old_time}
    )
    res_expired = run(_active_case(FakeUpdate(FakeMessage()), context))
    assert res_expired is None
