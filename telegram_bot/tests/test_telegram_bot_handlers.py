import asyncio
from types import SimpleNamespace

import pytest

from app.backend_client import BackendHTTPError, BackendUnavailableError
from app.bot import (
    AlbumDebouncer,
    _watch_for_case_result,
    callback_handler,
    checklist_command,
    handle_notification,
    image_document_handler,
    photo_handler,
    schemes_command,
    start_new_application,
    status_command,
    submit_command,
    text_handler,
    voice_handler,
)
from app.i18n import STRINGS
from app.notify import CallbackStore, render_notification
from app.onboarding import OnboardingStore


class FakeMessage:
    def __init__(
        self, *, text=None, voice=None, document=None, photo=None, media_group_id=None, caption=None
    ):
        self.text = text
        self.voice = voice
        self.document = document
        self.photo = photo
        self.media_group_id = media_group_id
        self.caption = caption
        self.replies = []
        self.deleted = False

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return SimpleNamespace(text=text)

    async def delete(self):
        self.deleted = True


class FakeBackend:
    def __init__(self, case=None):
        self.case = case or {"id": "case-1", "language": "en", "status": "collecting"}
        self.calls = []

    async def active_case(self, chat_id):
        self.calls.append(("active_case", chat_id))
        return self.case

    async def create_case(self, language, chat_id):
        self.calls.append(("create_case", language, chat_id))
        return {"case_id": "case-1", "language": language, "status": "COLLECTING"}

    async def send_document(self, case_id, content, **kwargs):
        self.calls.append(("document", case_id, content, kwargs))

    async def classify_document(self, case_id, document_id, doc_type):
        self.calls.append(("classify", case_id, document_id, doc_type))

    async def send_voice(self, case_id, content, **kwargs):
        self.calls.append(("voice", case_id, content, kwargs))

    async def send_text(self, case_id, text):
        self.calls.append(("text", case_id, text))

    async def start_case(self, case_id):
        self.calls.append(("start", case_id))

    async def answer(self, case_id, message_id, option):
        self.calls.append(("answer", case_id, message_id, option))

    async def delete_case(self, case_id):
        self.calls.append(("delete", case_id))

    async def get_schemes(self):
        return []


class FakeApplication:
    def __init__(self, backend):
        self.bot_data = {
            "backend": backend,
            "onboarding": OnboardingStore(),
        }


class FakeContext:
    def __init__(self, backend, bot=None):
        self.application = FakeApplication(backend)
        self.bot = bot or SimpleNamespace()


class FakeUpdate:
    def __init__(self, message, *, chat_id=42, callback_query=None):
        self.effective_message = message
        self.effective_chat = SimpleNamespace(id=chat_id)
        self.callback_query = callback_query


class FakeFileBot:
    def __init__(self):
        self.downloads = 0

    async def get_file(self, file_id):
        self.downloads += 1
        raise AssertionError("get_file must not be called")


class FakeCallbackQuery:
    def __init__(self, data, text="Question", reply_markup=None):
        self.data = data
        self.message = SimpleNamespace(text=text, reply_markup=reply_markup)
        self.answered = 0
        self.answer_calls = []
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered += 1
        self.answer_calls.append((args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


def run(coro):
    return asyncio.run(coro)


def test_notification_keyboard_uses_telegram_safe_callback_data():
    callbacks = CallbackStore()
    rendered = render_notification(
        {
            "text": "Choose one",
            "case_id": "a-very-long-case-identifier-that-never-goes-to-telegram",
            "message_id": "message-1234567890",
            "options": [{"label": "Yes", "idx": 1}, {"label": "No", "idx": 2}],
        },
        callbacks=callbacks,
    )

    keyboard = rendered[0][1]
    assert keyboard is not None
    for row in keyboard.inline_keyboard:
        for button in row:
            assert len(button.callback_data.encode("utf-8")) <= 64
            assert callbacks.pop(button.callback_data) is not None


def test_album_debounce_sends_one_ack_for_quiet_media_group():
    async def scenario():
        debouncer = AlbumDebouncer(delay=0.01)
        replies = []
        await debouncer.add(42, "album-1", lambda count: replies.append(count))
        await debouncer.add(42, "album-1", lambda count: replies.append(count))
        await debouncer.flush()
        return replies

    assert run(scenario()) == [2]


def test_pdf_is_rejected_without_download_or_backend_forward():
    backend = FakeBackend()
    message = FakeMessage(document=SimpleNamespace(file_id="pdf", mime_type="application/pdf"))
    context = FakeContext(backend, bot=FakeFileBot())

    run(image_document_handler(FakeUpdate(message), context))

    assert message.replies
    assert "PDF" in message.replies[0][0]
    assert context.bot.downloads == 0
    assert not any(call[0] == "document" for call in backend.calls)


def test_image_document_file_is_forwarded_acknowledged_and_deleted():
    class ImageFileBot:
        async def get_file(self, file_id):
            class File:
                async def download_as_bytearray(self):
                    return bytearray(b"image-bytes")

            return File()

    backend = FakeBackend()
    message = FakeMessage(
        document=SimpleNamespace(
            file_id="image",
            mime_type="image/jpeg",
            file_name="land-record.jpg",
        )
    )
    context = FakeContext(backend, bot=ImageFileBot())

    run(image_document_handler(FakeUpdate(message), context))

    assert any(call[0] == "document" for call in backend.calls)
    assert message.deleted
    assert message.replies
    assert "1 document(s) received" in message.replies[0][0]
    keyboard = message.replies[0][1]["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "➕ Add another document"
    assert keyboard.inline_keyboard[1][0].text == "✅ Check eligibility"


def test_overlong_voice_is_rejected_before_download():
    backend = FakeBackend()
    message = FakeMessage(voice=SimpleNamespace(file_id="voice", duration=31))
    context = FakeContext(backend, bot=FakeFileBot())

    run(voice_handler(FakeUpdate(message), context))

    assert message.replies
    assert "too long" in message.replies[0][0]
    assert context.bot.downloads == 0
    assert not any(call[0] == "voice" for call in backend.calls)


def test_question_callback_answers_backend_and_removes_keyboard():
    callbacks = CallbackStore()
    rendered = render_notification(
        {
            "text": "Question",
            "case_id": "case-1",
            "message_id": "m-1",
            "options": [{"label": "Yes", "idx": 1}],
        },
        callbacks=callbacks,
    )
    token = rendered[0][1].inline_keyboard[0][0].callback_data
    backend = FakeBackend()
    query = FakeCallbackQuery(token)
    message = FakeMessage()
    context = FakeContext(backend)
    context.application.bot_data["callbacks"] = callbacks

    run(callback_handler(FakeUpdate(message, callback_query=query), context))

    assert query.answered == 1
    assert ("answer", "case-1", "m-1", 1) in backend.calls
    assert query.edits and query.edits[0][1]["reply_markup"] is None
    assert "Answer recorded" in query.edits[0][0]


def test_consent_callback_sends_reply_keyboard_in_a_new_message():
    backend = FakeBackend()
    context = FakeContext(backend)
    callbacks = context.application.bot_data.setdefault("callbacks", CallbackStore())
    token = callbacks.add_action("consent:yes")
    query = FakeCallbackQuery(token)
    message = FakeMessage()

    run(callback_handler(FakeUpdate(message, callback_query=query), context))

    assert ("create_case", "en", 42) in backend.calls
    assert query.edits and query.edits[0][1]["reply_markup"] is None
    assert "Consent recorded" in query.edits[0][0]
    assert message.replies
    keyboard = message.replies[0][1]["reply_markup"]
    labels = {button.text for row in keyboard.keyboard for button in row}
    assert {"Start new application", "Continue / status", "Browse schemes"}.issubset(labels)
    assert "What I uploaded" not in " ".join(labels)
    assert "Cancel application" not in " ".join(labels)


def test_submit_command_reports_backend_unavailable_instead_of_raising():
    class UnavailableBackend(FakeBackend):
        async def active_case(self, chat_id):
            raise BackendUnavailableError

    message = FakeMessage()
    context = FakeContext(UnavailableBackend())

    run(submit_command(FakeUpdate(message), context))

    assert message.replies
    assert "cannot reach the case service" in message.replies[0][0]


def test_text_upload_is_acknowledged_with_next_step():
    backend = FakeBackend()
    message = FakeMessage(text="I need help")
    context = FakeContext(backend)

    run(text_handler(FakeUpdate(message), context))

    assert ("text", "case-1", "I need help") in backend.calls
    assert message.replies
    assert "STEP 1 complete" in message.replies[0][0]
    assert "upload" in message.replies[0][0].lower()
    assert message.replies[0][1]["reply_markup"].keyboard


@pytest.mark.parametrize(
    ("language", "done_label", "working_marker"),
    [
        ("en", "Done", "Submission received."),
        ("ta", "முடிந்தது", "சமர்ப்பிப்பு பெறப்பட்டது."),
        ("te", "పూర్తయింది", "సమర్పణ అందింది."),
        ("hi", "पूरा हुआ", "सबमिशन मिल गया।"),
    ],
)
def test_typed_localized_done_starts_case_and_sends_working_ack(
    language, done_label, working_marker
):
    backend = FakeBackend(case={"id": "case-1", "language": language, "status": "collecting"})
    message = FakeMessage(text=done_label)
    context = FakeContext(backend)

    run(text_handler(FakeUpdate(message), context))

    assert ("start", "case-1") in backend.calls
    assert not any(call[0] == "text" for call in backend.calls)
    assert message.replies and working_marker in message.replies[0][0]


def test_non_done_text_still_forwards_as_citizen_intent():
    backend = FakeBackend()
    message = FakeMessage(text="Done for today, but I have another question")
    context = FakeContext(backend)

    run(text_handler(FakeUpdate(message), context))

    assert ("text", "case-1", "Done for today, but I have another question") in backend.calls
    assert not any(call[0] == "start" for call in backend.calls)


class DownloadingFileBot:
    async def get_file(self, file_id):
        class File:
            async def download_as_bytearray(self):
                return bytearray(b"voice-bytes")

        return File()


def test_voice_upload_is_acknowledged_after_backend_receives_it():
    backend = FakeBackend()
    message = FakeMessage(voice=SimpleNamespace(file_id="voice", duration=3))
    context = FakeContext(backend, bot=DownloadingFileBot())

    run(voice_handler(FakeUpdate(message), context))

    assert any(call[0] == "voice" for call in backend.calls)
    assert message.replies
    assert "STEP 1 complete" in message.replies[0][0]


def test_done_422_explains_missing_document_without_exposing_backend_detail():
    class StartBackend(FakeBackend):
        async def start_case(self, case_id):
            raise BackendHTTPError(422, {"detail": "upload at least one document first"})

    # The callback path uses the active case lookup, then edits the Done message.
    from app.bot import callback_handler

    backend = StartBackend()
    query = FakeCallbackQuery("start:done", text="Send your inputs")
    context = FakeContext(backend)
    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    assert query.edits
    assert "at least one document" in query.edits[0][0]
    assert "upload at least one document first" not in query.edits[0][0]


def test_status_includes_next_action_and_recent_citizen_safe_messages():
    backend = FakeBackend(
        case={
            "id": "case-1",
            "language": "en",
            "status": "NEEDS_DOCUMENTS",
            "messages": [{"text": "Please send your land record.", "kind": "info"}],
        }
    )
    message = FakeMessage()
    context = FakeContext(backend)

    run(status_command(FakeUpdate(message), context))

    assert message.replies
    text = message.replies[0][0]
    assert "NEEDS_DOCUMENTS" in text
    assert "Send the missing document" in text
    assert "Please send your land record." in text


def test_status_rebuilds_pending_question_buttons_after_bot_restart():
    backend = FakeBackend(
        case={
            "id": "case-1",
            "language": "en",
            "channel_ref": "42",
            "status": "NEEDS_INFO",
            "messages": [
                {
                    "id": "question-1",
                    "kind": "question",
                    "text": "Does anyone pay income tax?",
                    "options": [{"label": "Yes", "idx": 1}, {"label": "No", "idx": 2}],
                }
            ],
        }
    )
    message = FakeMessage()
    context = FakeContext(backend)

    run(status_command(FakeUpdate(message), context))

    keyboard = message.replies[0][1]["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "Yes"
    assert keyboard.inline_keyboard[1][0].text == "No"
    target = context.application.bot_data["callbacks"].get(
        keyboard.inline_keyboard[0][0].callback_data
    )
    assert target and target.message_id == "question-1" and target.chat_id == "42"


def test_persistent_menu_labels_are_localized_and_include_welfare_actions():
    backend = FakeBackend()
    message = FakeMessage()
    context = FakeContext(backend)

    run(status_command(FakeUpdate(message), context))

    keyboard = message.replies[0][1]["reply_markup"]
    labels = {button.text for row in keyboard.keyboard for button in row}
    assert {"Start new application", "Continue / status", "Browse schemes"}.issubset(labels)
    assert {"Help", "Delete data", "Language / privacy"}.issubset(labels)
    assert keyboard.is_persistent is True


def test_schemes_flow_presents_backend_catalog_without_bot_eligibility_claims():
    class SchemesBackend(FakeBackend):
        async def get_schemes(self):
            return [
                {
                    "scheme_id": "pm_kisan_mock",
                    "name": "PM-Kisan (MOCK, simplified)",
                    "benefit": "INR 6,000 per year (MOCK benefit)",
                    "required_documents": ["aadhaar", "land_record"],
                }
            ]

    message = FakeMessage()
    context = FakeContext(SchemesBackend())
    run(schemes_command(FakeUpdate(message), context))

    assert len(message.replies) == 2
    assert "PM-Kisan (MOCK, simplified)" in message.replies[0][0]
    assert "land_record" in message.replies[0][0]
    assert "does not decide eligibility" in message.replies[1][0]
    button = message.replies[1][1]["reply_markup"].inline_keyboard[0][0]
    assert len(button.callback_data.encode()) <= 64
    assert button.callback_data.startswith("u:")


def test_start_new_application_requires_confirmation_when_case_is_active():
    message = FakeMessage()
    context = FakeContext(FakeBackend())
    run(start_new_application(FakeUpdate(message), context))

    assert message.replies
    assert "delete that case" in message.replies[0][0]
    keyboard = message.replies[0][1]["reply_markup"]
    callback_data = keyboard.inline_keyboard[0][0].callback_data
    assert callback_data.startswith("u:")
    assert "case-1" not in callback_data


def test_confirmed_restart_deletes_old_case_before_new_onboarding():
    backend = FakeBackend()
    message = FakeMessage()
    context = FakeContext(backend)
    run(start_new_application(FakeUpdate(message), context))
    token = message.replies[0][1]["reply_markup"].inline_keyboard[0][0].callback_data

    query = FakeCallbackQuery(token)
    run(callback_handler(FakeUpdate(message, callback_query=query), context))

    assert ("delete", "case-1") in backend.calls
    assert query.edits and "previous case was deleted" in query.edits[0][0]
    assert len(message.replies) == 3


def test_continue_active_case_callback_shows_guidance_and_buttons():
    backend = FakeBackend(
        case={
            "id": "case-1",
            "language": "en",
            "status": "NEEDS_DOCUMENTS",
            "documents": [{"doc_type": "aadhaar"}, {"doc_type": "land_record"}],
        }
    )
    context = FakeContext(backend)
    callbacks = context.application.bot_data.setdefault("callbacks", CallbackStore())
    token = callbacks.add_action("case:continue")
    query = FakeCallbackQuery(token)

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    assert query.answered == 1
    assert query.edits
    edited_text = query.edits[0][0]
    assert "Continuing Active Application" in edited_text
    assert "Aadhaar Card" in edited_text
    assert "Land Record" in edited_text
    assert "Bank Passbook" in edited_text
    reply_markup = query.edits[0][1]["reply_markup"]
    assert reply_markup is not None
    assert reply_markup.inline_keyboard[1][0].text == "✅ Check eligibility"


def test_stale_callback_is_acknowledged_without_backend_call():
    backend = FakeBackend()
    query = FakeCallbackQuery("a:stale")
    context = FakeContext(backend)

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    assert query.answered == 1
    assert not any(call[0] == "answer" for call in backend.calls)
    assert query.edits and "no longer available" in query.edits[0][0]


def test_checklist_command_shows_documents_and_done_button():
    backend = FakeBackend(
        case={
            "id": "case-1",
            "language": "en",
            "status": "collecting",
            "documents": [{"doc_type": "aadhaar"}, {"doc_type": "land_record"}],
        }
    )
    message = FakeMessage()
    context = FakeContext(backend)
    run(checklist_command(FakeUpdate(message), context))

    assert message.replies
    text = message.replies[0][0]
    assert "Uploaded documents (2)" in text
    assert "Aadhaar Card" in text
    assert "Land Record" in text
    assert "PM-Kisan" in text
    reply_markup = message.replies[0][1]["reply_markup"]
    assert reply_markup.inline_keyboard[1][0].text == "✅ Check eligibility"


def test_text_handler_case_insensitive_done_submits_case():
    for word in ("done", "Done", "DONE", "submit", "Submit", "apply", "/done"):
        backend = FakeBackend()
        message = FakeMessage(text=word)
        context = FakeContext(backend)

        run(text_handler(FakeUpdate(message), context))

        assert ("start", "case-1") in backend.calls
        assert any("Submission received" in reply[0] for reply in message.replies)


def test_result_notification_is_deduplicated_by_message_id():
    class ResultBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    bot = ResultBot()
    application = SimpleNamespace(bot=bot, bot_data={"callbacks": CallbackStore()})
    payload = {
        "chat_id": "42",
        "case_id": "case-1",
        "kind": "result",
        "language": "en",
        "message_id": "result-1",
        "text": "Outcome: ELIGIBLE",
    }

    run(handle_notification(payload, application))
    run(handle_notification(payload, application))

    assert len(bot.sent) == 1


def test_concurrent_duplicate_notifications_are_claimed_before_send():
    async def scenario():
        class BlockingBot:
            def __init__(self):
                self.sent = []
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def send_message(self, **kwargs):
                self.sent.append(kwargs)
                self.started.set()
                await self.release.wait()

        bot = BlockingBot()
        application = SimpleNamespace(bot=bot, bot_data={"callbacks": CallbackStore()})
        payload = {
            "chat_id": "42",
            "case_id": "case-1",
            "kind": "result",
            "language": "en",
            "message_id": "result-concurrent",
            "text": "Outcome: ELIGIBLE",
        }
        first = asyncio.create_task(handle_notification(payload, application))
        await bot.started.wait()
        second = asyncio.create_task(handle_notification(payload, application))
        await asyncio.sleep(0)
        bot.release.set()
        await asyncio.gather(first, second)
        return len(bot.sent)

    assert run(scenario()) == 1


def test_question_callback_rejects_a_different_chat():
    callbacks = CallbackStore()
    rendered = render_notification(
        {
            "text": "Choose one",
            "case_id": "case-1",
            "message_id": "question-1",
            "chat_id": "42",
            "options": [{"label": "Yes", "idx": 1}],
        },
        callbacks=callbacks,
    )
    token = rendered[0][1].inline_keyboard[0][0].callback_data
    backend = FakeBackend()
    query = FakeCallbackQuery(token)
    context = FakeContext(backend)
    context.application.bot_data["callbacks"] = callbacks

    run(callback_handler(FakeUpdate(FakeMessage(), chat_id=43, callback_query=query), context))

    assert not any(call[0] == "answer" for call in backend.calls)
    assert query.edits and "no longer available" in query.edits[0][0]


def test_every_supported_locale_has_the_same_ui_keys():
    keys = set(STRINGS["en"])
    assert all(set(strings) == keys for strings in STRINGS.values())


def test_result_watcher_delivers_persisted_result_when_push_is_missing(monkeypatch):
    class ResultBackend:
        async def get_case(self, case_id):
            return {
                "case_id": case_id,
                "channel_ref": "42",
                "status": "COMPLETED",
                "messages": [
                    {
                        "id": "result-1",
                        "kind": "result",
                        "text": "Outcome: ELIGIBLE",
                        "options": [],
                    }
                ],
            }

    class ResultBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, **kwargs):
            self.sent.append(kwargs)

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr("app.bot.asyncio.sleep", no_wait)
    bot = ResultBot()
    application = SimpleNamespace(bot=bot, bot_data={"callbacks": CallbackStore()})

    run(
        _watch_for_case_result(
            application,
            ResultBackend(),
            "case-1",
            "en",
            set(),
            attempts=1,
        )
    )

    assert len(bot.sent) == 1
    assert "Outcome: ELIGIBLE" in bot.sent[0]["text"]


def test_photo_handler_with_caption_tags_and_reassures_dpdp():
    class PhotoFileBot:
        async def get_file(self, file_id):
            class File:
                async def download_as_bytearray(self):
                    return bytearray(b"photo-bytes")

            return File()

    backend = FakeBackend()
    message = FakeMessage(
        photo=[SimpleNamespace(file_id="p1", file_size=1024)],
        caption="Here is my Aadhaar card photo",
    )
    context = FakeContext(backend, bot=PhotoFileBot())

    run(photo_handler(FakeUpdate(message), context))

    assert message.deleted
    assert any(
        call[0] == "document" and call[3].get("doc_type") == "aadhaar" for call in backend.calls
    )
    assert message.replies
    text = message.replies[0][0]
    assert "Aadhaar Card" in text
    assert "DPDP" in text
    assert "Check eligibility" in text


def test_callback_handler_tag_action_classifies_document():
    backend = FakeBackend()
    context = FakeContext(backend)
    store = context.application.bot_data.setdefault("callbacks", CallbackStore())
    token = store.add_action("tag:doc-456:land_record")
    query = FakeCallbackQuery(token)

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    assert ("classify", "case-1", "doc-456", "land_record") in backend.calls
    assert query.edits
    assert "Land Record" in query.edits[0][0]


def test_callback_action_resolution_recovers_legacy_and_unmapped_tokens():
    backend = FakeBackend(
        case={
            "id": "case-999",
            "language": "en",
            "status": "NEEDS_DOCUMENTS",
            "documents": [{"doc_type": "aadhaar"}],
        }
    )
    context = FakeContext(backend)

    # Simulate an inline button that has a legacy token or lost in-memory token
    fake_btn = SimpleNamespace(text="Continue active case", callback_data="u:legacy_token_123")
    fake_markup = SimpleNamespace(inline_keyboard=[[fake_btn]])
    query = FakeCallbackQuery(
        "u:legacy_token_123",
        text="Application status",
        reply_markup=fake_markup,
    )

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    assert query.edits
    edited_text = query.edits[0][0]
    assert "Continuing Active Application" in edited_text
    assert "Missing Document Required" in edited_text


def test_case_continue_eliminates_duplicate_backend_get_calls():
    backend = FakeBackend(
        case={
            "id": "case-123",
            "language": "en",
            "status": "NEEDS_DOCUMENTS",
            "documents": [{"doc_type": "aadhaar"}],
        }
    )
    context = FakeContext(backend)
    store = context.application.bot_data.setdefault("callbacks", CallbackStore())
    token = store.add_action("case:continue")
    query = FakeCallbackQuery(token)

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    # active_case should be called exactly once during the entire callback lifecycle
    active_case_calls = [c for c in backend.calls if c[0] == "active_case"]
    assert len(active_case_calls) == 1
    assert query.edits
    assert "Continuing Active Application" in query.edits[0][0]


def test_callback_handler_answers_fast_with_toast_on_check_and_add():
    backend = FakeBackend(
        case={
            "id": "case-555",
            "language": "en",
            "status": "COLLECTING",
            "documents": [],
        }
    )
    context = FakeContext(backend)
    store = context.application.bot_data.setdefault("callbacks", CallbackStore())

    # Test case:add
    add_token = store.add_action("case:add")
    add_query = FakeCallbackQuery(add_token)
    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=add_query), context))
    assert any("document photo" in str(c) for c in add_query.answer_calls)

    # Test case:check
    check_token = store.add_action("case:check")
    check_query = FakeCallbackQuery(check_token)
    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=check_query), context))
    assert any("Evaluating eligibility" in str(c) for c in check_query.answer_calls)
    assert ("start", "case-555") in backend.calls


def test_question_answer_recovery_after_bot_restart():
    backend = FakeBackend(
        case={
            "id": "case-777",
            "language": "en",
            "status": "NEEDS_INFO",
            "messages": [
                {
                    "id": "msg-q1",
                    "kind": "question",
                    "text": "Do you own land?",
                    "options": [{"label": "Yes", "idx": 1}],
                }
            ],
        }
    )
    context = FakeContext(backend)

    # An answer token that was lost from memory due to restart
    fake_btn = SimpleNamespace(text="Yes", callback_data="a:lost_secret")
    fake_markup = SimpleNamespace(inline_keyboard=[[fake_btn]])
    query = FakeCallbackQuery("a:lost_secret", text="Do you own land?", reply_markup=fake_markup)

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    assert ("answer", "case-777", "msg-q1", "Yes") in backend.calls
    assert query.edits
    assert "Answer recorded" in query.edits[0][0]


def test_question_answer_no_button_does_not_trigger_consent_no():
    """Verify that answering 'No' to a question records the answer and does not decline consent."""
    backend = FakeBackend(
        case={
            "id": "case-888",
            "language": "en",
            "status": "NEEDS_INFO",
            "messages": [
                {
                    "id": "msg-q2",
                    "kind": "question",
                    "text": "Does anyone in your family pay income tax?",
                    "options": [{"label": "Yes", "idx": 1}, {"label": "No", "idx": 2}],
                }
            ],
        }
    )
    context = FakeContext(backend)

    fake_btn = SimpleNamespace(text="No", callback_data="a:test_no_secret")
    fake_markup = SimpleNamespace(inline_keyboard=[[fake_btn]])
    query = FakeCallbackQuery(
        "a:test_no_secret",
        text="Does anyone in your family pay income tax?",
        reply_markup=fake_markup,
    )

    run(callback_handler(FakeUpdate(FakeMessage(), callback_query=query), context))

    # Must call answer, NOT decline consent
    assert ("answer", "case-888", "msg-q2", "No") in backend.calls
    assert query.edits
    assert "No problem. No application was created" not in query.edits[0][0]
    assert "Answer recorded" in query.edits[0][0]


def test_browse_schemes_action_handler():
    """Verify that case:browse_schemes action triggers schemes listing."""
    backend = FakeBackend(
        case={
            "id": "case-999",
            "language": "en",
            "status": "COLLECTING",
        }
    )
    context = FakeContext(backend)
    store = context.application.bot_data.setdefault("callbacks", CallbackStore())
    token = store.add_action("case:browse_schemes")
    message = FakeMessage()
    query = FakeCallbackQuery(token, text="Active")

    run(callback_handler(FakeUpdate(message, callback_query=query), context))

    assert len(message.replies) >= 1
    assert "PM-Kisan" in message.replies[0][0]


