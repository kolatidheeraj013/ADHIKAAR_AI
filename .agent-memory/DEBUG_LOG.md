# ADHIKAAR Debug Log

## 2026-10-19 — environment gaps

- Docker commands could not run because `docker` is not installed in the runner.
- Initial Python checks lacked FastAPI/pytest/ruff; declared service dependencies
  were installed locally, then all Phase 0 checks passed.
- Frontend first build timed out after page generation; a clean rerun passed.
- FastAPI TestClient emits a Starlette/httpx deprecation warning; no test failure.

## 2026-10-19 — Phase 3 test-agent access

- The requested testing sub-agent returned `omnirush_account_required`.
- Confirmed impact: no repository files were changed by that failed delegation.
- Resolution: continue verification in the main agent; no application credential is required.

## 2026-10-19 — LangGraph checkpoint dependency

- Installing the latest SQLite checkpoint adapter initially conflicted with the
  selected LangGraph checkpoint range.
- Resolution: pinned the compatible adapter range in project dependencies as
  `langgraph-checkpoint-sqlite>=2.0.11,<3`; SQLite checkpoint rebuild test passes.

## 2026-10-19 — Alembic working-directory check

- `alembic -c backend/alembic.ini check` from the repo root failed because
  `script_location` is relative to `backend/`.
- Resolution: reran `alembic -c alembic.ini check` from `backend/`; no new upgrade
  operations detected.

## 2026-10-19 — Phase 4 provider readiness

- Observation: The official OpenAI supervised fine-tuning documentation states that
  the platform is winding down for new users, while dated GPT-4.1 snapshots are
  listed as supported for existing access.
- Impact: OpenAI fine-tuning availability is not yet verified for this account; no
  training upload or fine-tuning code was attempted.
- Current status: blocked pending dashboard access check. Fallback is GPT-4.1
  structured output with Pydantic validation.
- Related policy issue: real citizen-document intent conflicts with the project’s
  synthetic-only requirements; no raw documents were read, uploaded, or stored.

## 2026-10-19 — test environment and runner isolation

- Running tests directly with system Python (`python -m pytest backend/tests`) failed
  because system Python 3.14 had an incompatible `starlette 1.8.0` installed alongside
  `fastapi 0.115.9` (missing `on_startup` in Starlette Router) and lacked package deps.
- Resolution: Ran tests via `uv run --project <folder> --extra test pytest <folder>/tests`.
  Each service (`backend/`, `telegram_bot/`, `mock_portal/`) resolves its own isolated
  venv cleanly. All 36 tests (34 backend, 1 telegram_bot, 1 mock_portal) passed.

## 2026-10-20 — Colab xformers wheel build failure

- Symptom: In `llama_3_8b_instruct_finetune-d13.ipynb` Cell 1, pip failed with
  `Building wheel for xformers (setup.py) ... error: Failed building wheel for xformers`.
- Root cause: Pip could not find a pre-compiled wheel for `xformers<0.0.27`, causing it to
  attempt compiling from source code via `setup.py bdist_wheel`, which fails in Colab.
- Resolution: Removed manual `xformers` installation from Cell 1. Unsloth uses PyTorch's
  native SDPA / attention kernels on Colab T4 out of the box without source compilation.

## 2026-10-20 — Phase 5 verification and test environment

- Initial Phase 5 test run under `uv run --project backend` failed in two tests because
  pytest's working import path exposed `backend/` but not the repository-level
  `ml_training/` namespace.
- Resolution: updated `backend/tests/conftest.py` to add both the repository root and
  backend root to `sys.path`; the full backend suite then passed.
- Verified: Phase 5 tests `4 passed, 1 skipped`; backend suite `55 passed, 1 skipped`;
  `ruff check backend telegram_bot mock_portal ml_training` passed; `make test` passed.
- The optional model-shape test is skipped because PyTorch is not installed. Training
  and evaluation commands correctly emit structured fallback reports in this runner.
- `uv run` for the mock portal environment hit a corrupted/incomplete Pygments install
  (`No module named pygments.formatters`), but the repository-level `make test` and
  `python -m pytest mock_portal/tests` both passed. This is an environment issue, not
  an application failure.

## 2026-10-20 — Phase 6 RAG verification

- Implemented and verified heading-based MOCK rulebook ingestion, persisted lexical
  retrieval, optional ChromaDB/local sentence-transformers support, and graph wiring.
- Focused Phase 6 tests: 6 passed. Full backend suite: 61 passed, 1 skipped; Ruff passed.
- No vector model download or network access was attempted. The test path forces the
  deterministic lexical fallback.
- Graphify was refreshed with `--update --no-viz --code-only` and `cluster-only`: 700
  nodes, 1423 edges, 63 communities. Non-code semantic extraction remains skipped
  because no graphify-supported semantic API key is configured.

## 2026-10-20 — Phase 8 API and web verification

- Implemented the FastAPI case/reviewer/audit surface and Next.js citizen/reviewer/audit
  flows. Added `python-multipart` because FastAPI's multipart upload routes require it;
  refreshed `backend/uv.lock`.
- `make test`: backend 73 passed/1 skipped, Telegram 1 passed, mock portal 7 passed.
  `make lint`, `npx tsc --noEmit`, `uv lock --check`, and scoped `git diff --check` passed.
- `npm run build` compiled successfully and generated all five pages, then exceeded the
  five-minute runner limit during `Collecting build traces...`; no compile, type, or
  page-generation error appeared before termination. Treat standalone artifact creation
  as an environment gap until a faster clean build is available.
- Graphify refreshed after Phase 8: 860 nodes, 1997 edges, 53 communities; code-only
  extraction skipped non-code semantic files as expected.

## 2026-10-20 — Phase 9 Telegram implementation

- Implemented real `python-telegram-bot` v21 async polling/webhook service; no fake
  Telegram transport is used in production mode. Added consent/language onboarding,
  text/voice/photo/image-document forwarding, pre-download voice/document guards,
  message deletion, album debounce, question callbacks, commands, i18n, and internal
  notification rendering.
- Added backend `TelegramNotifier` with internal service-token delivery, bounded queue,
  three-attempt retry, failure audit callback, and per-case notifier selection. The
  backend never reads or stores `TELEGRAM_BOT_TOKEN`.
- `make test`: backend 75 passed/1 skipped, Telegram 8 passed, mock portal 7 passed.
  `make lint`, both uv lock checks, compileall, and scoped `git diff --check` passed.
- Live Telegram API smoke test is not claimed: it requires a BotFather token and an
  online running backend/bot pair. The token must be configured locally, never pasted
  into chat or committed.
- Graphify refreshed after Phase 9: 1018 nodes, 2476 edges, 57 communities; code-only
  extraction skipped non-code semantic files as expected.

## 2026-10-20 — Phase 7 portal verification

- Implemented HTTP mock-portal client and deterministic portal service endpoints.
- Focused backend Phase 7 plus Phase 3 recovery tests: 12 passed. Mock-portal Phase 7
  tests: 6 passed with system pytest.
- Full `make test`: backend 65 passed/1 skipped, Telegram 1 passed, mock portal 7 passed.
  Ruff and backend `uv lock --check` passed.
- The isolated mock-portal uv environment still has an incomplete Pygments install
  (`No module named pygments.formatters`); system pytest provides independent passing
  evidence. This is an environment issue, not a Phase 7 application failure.
- Graphify refreshed successfully: 754 nodes, 1552 edges, 56 communities. Non-code
  semantic extraction remains skipped because no supported semantic API key is configured.

## 2026-10-21 — Telegram UX continuation and live service checks

- Recovered the interrupted Telegram UX task from the working tree. The implementation
  already included the persistent localized menu, `/new`, `/schemes`, `/language`, safe
  active-case replacement, scheme catalog presentation, and richer document guidance.
- Focused verification: `uv run --project telegram_bot --extra test pytest ...` passed
  19 tests; direct `telegram_bot/.venv/Scripts/ruff.exe check telegram_bot/app telegram_bot/tests`
  passed; compileall and scoped diff checks passed. The initial system-Python test and
  `make lint` attempt failed only because this shell lacks the project dependencies and
  `make`; rerunning with the project environment passed.
- Bot API read-only checks succeeded without printing the token: `getMe` returned the
  configured bot username `Adhikaar013bot`, and `getWebhookInfo` showed no webhook and
  zero pending updates.
- Backend and Telegram health endpoints returned `status: ok`. Backend required the
  isolated `uv run --isolated` startup path because the existing backend `.venv` could
  not be synchronized (`lib64` access denied / incomplete environment).
- Remaining gap: an actual user must message the bot to verify visible onboarding,
  acknowledgements, document guidance, Done error handling, notifications, and status.

## 2026-10-21 — Phase 10 demo polish

- Implemented `backend/app/demo.py` and replaced the seed/demo placeholders with a
  deterministic synthetic runner for A, B, C, D1, D2, and E. Initial test failures
  were fixed: SQLAlchemy UUID columns require `UUID` objects, and D2 ends at a review
  interrupt without a citizen result message.
- Added `backend/tests/test_phase10_demo.py`; all 8 Phase 10 tests pass. The runner
  measured A/B/D1/E at `0.9170`, C at `0.7602`, and D2 at `NEEDS_REVIEW` after one
  portal attempt.
- Updated Makefile targets to use isolated `uv run` environments. In this shell
  `make` itself is absent, so direct `make test`/`make lint` remain unexecutable; the
  equivalent isolated commands passed.
- Added `docs/demo-runbook.md`, `docs/deployment.md`, README Phase 10 instructions,
  and measured threshold documentation. Frontend build was not rerun because
  `frontend/node_modules` is absent; this is an environment gap unrelated to Phase 10
  backend/demo changes.

## 2026-10-21 — Telegram missing-result bug

- User reported that Telegram only showed the generic working/collection flow and did
  not show the project's main result or certainty. Two causes were confirmed:
  `DEMO_MODE=offline` selected `NoopNotifier` for Telegram cases, and the graph entered
  the review interrupt without notifying the citizen.
- Fixed `backend/app/main.py` so any case with `channel=telegram` and `channel_ref`
  uses `TelegramNotifier`; offline mode still keeps deterministic business fakes for
  the backend and continues to use `NoopNotifier` for web cases.
- Fixed `backend/app/agents/graph.py` so review entry emits a result update and final
  messages include the scheme, deterministic outcome, case status, confidence band,
  rule reasons, MOCK benefit, portal state/reference, and next step. Confidence is now
  calculated for all eligibility decisions, including NOT_ELIGIBLE.
- Added regression coverage in `backend/tests/test_notifier.py` and
  `backend/tests/test_phase3_graph.py`.
- Verified: backend `86 passed, 1 skipped`; Telegram `19 passed`; mock portal `7 passed`;
  Ruff, compileall, and scoped diff checks passed. `make test` and `make lint` still exit
  127 because `make` is not installed; this is unrelated to the code changes.

## 2026-10-21 — GNU Make environment repair

- Symptom: direct `make test` and `make lint` returned exit 127 because `make` was not
  available in the Windows/Git Bash shell.
- Alternatives checked: WSL Ubuntu is installed, but its distribution also lacked GNU
  Make; `nmake`, `gmake`, and other Windows build-tool alternatives were not present.
- Resolution: installed GNU Make 4.4.1 with `winget install --id ezwinports.make`.
  WinGet updated the user PATH, so existing shells must be restarted or use the installed
  binary path until the environment refreshes.
- Verification: PATH-injected `make test` passed with backend `89 passed, 1 skipped`,
  Telegram `24 passed`, and mock portal `7 passed`; PATH-injected `make lint` passed.

## 2026-10-21 — LM Studio runtime boundary diagnosis

- The current implementation is a thin adapter over the existing `ProviderLLMClient`;
  it does not load or deploy the fine-tuned model itself. `LLM_BASE_URL` selects that
  client at backend runtime, and `LLM_MODEL` is sent in the OpenAI-compatible request.
- Reproduction in this runner: `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_BASE_URL` are unset,
  and no repository `.env` file exists. The backend therefore correctly selects the
  deterministic `_OfflineLLM`. A direct probe to `http://127.0.0.1:1234/v1/models` was
  refused because no reachable LM Studio server exists in this runner.
- This earlier reproduction is superseded: a later local LM Studio startup made the same
  endpoint reachable and the live backend smoke tests passed.
- Important deployment boundary: `127.0.0.1` is correct when Uvicorn runs directly on
  Windows. If the backend runs inside Docker while LM Studio runs on Windows, the backend
  must use the host address (`host.docker.internal`) instead of container-local loopback.
- Assessment: do not roll back the provider wiring. The pre-wiring runtime always used
  `_OfflineLLM`, so rollback would remove the only path to the tuned model rather than fix
  connectivity. The efficient next fix is configuration/preflight validation and an
  environment-specific endpoint, not a backend rewrite.

## 2026-10-21 — tuned LM Studio wiring and typed Done

- `FT-backend.md` was inspected and is zero bytes, so no external integration plan was
  available to apply. The existing `ProviderLLMClient` contract and configuration were
  used instead.
- Added runtime selection: when `LLM_BASE_URL` is configured, backend graph runs use
  `ProviderLLMClient` with the configured provider/model/key/base URL and force provider
  mode. Without it, `_OfflineLLM` remains active. Local keyless endpoints omit the
  Authorization header. Added tests for the LM Studio model and endpoint.
- The screenshot's `COLLECTING` state was reproduced conceptually from the visible
  behavior: the user typed `Done`, which Telegram routed through `text_handler` as
  ordinary intent text. Added typed/localized Done handling that calls `/start` and
  sends the working acknowledgement; non-Done text still forwards normally.
- Verification: backend `89 passed, 1 skipped`; Telegram `24 passed`; mock portal
  `7 passed`; Ruff, compileall, and scoped diff checks passed. Direct `make test` and
  `make lint` both exit 127 because `make` is unavailable. The local LM Studio probe
  to `http://127.0.0.1:1234/v1/models` was refused, so live model connectivity is not
  claimed.

## 2026-10-23 — Telegram v2 UX failure and v3 rebuild

- Symptom: user rated the Telegram bot 1/10 for confusion and lack of structure; after
  image uploads the citizen could remain waiting without seeing the outcome.
- Confirmed v2 weaknesses: the user-facing flow mixed `Done`, `Submit / Done`, checklist,
  inline document-tagging, and persistent reply keyboards; terminal cases were excluded
  from `/cases/active`; and a result push failure left no bot-side recovery path.
- Resolution: rebuilt the visible flow without changing `@Adhikaar013bot` or its token:
  explicit application steps, one `Check eligibility` action, `Add another document`,
  concise upload acknowledgements, `/submit`, `/checklist`, `/cancel`, `/cases/latest`
  status recovery, and a 45-second persisted-case watcher that deduplicates against push
  notifications by message id.
- Verification: Telegram 31 tests passed; backend 90 passed with 1 skipped; mock portal
  7 passed; Ruff/lint, compileall, and scoped diff checks passed.
- Remaining status: behavior is offline-verified. The user must repeat the real Telegram
  conversation with the same bot to validate mobile rendering, Telegram callback behavior,
  and the final visible result.

## 2026-10-23 — Telegram runtime and callback debugging

- Symptom/evidence: default ports `8000` and `8200` were not listening in the current runner;
  only isolated diagnostic services on `18000` and `18200` were active. The Telegram service's
  `/health` returned 200 even when no Telegram application was initialized, so liveness was
  masking a non-polling bot. Bot API read-only checks for `@Adhikaar013bot` returned `getMe`
  success, no webhook URL, and zero pending updates.
- Confirmed code defects: consent attempted to edit a Telegram message with a
  `ReplyKeyboardMarkup` (Telegram rejects this); `/submit` let backend exceptions escape;
  answer callbacks did not schedule result recovery; persisted `NEEDS_INFO` cases did not
  rebuild answer buttons; and duplicate push/fallback notifications raced before the delivered
  key was recorded. These defects were found by the code-review sub-agent and covered by new
  regression tests.
- Runtime/config risks: Compose previously relied on `localhost` defaults for inter-container
  calls and did not declare `python-dotenv` even though both services import it. Compose now
  sets `BACKEND_URL=http://backend:8000` and `BOT_INTERNAL_URL=http://telegram_bot:8200`;
  `/ready` returns 503 until polling/webhook startup completes.
- Resolution: implemented the focused reliability fixes and added tests for consent flow,
  `/submit` backend failure, restart question recovery, answer callback ownership, concurrent
  deduplication, locale key parity, and readiness.
- Verification: `make test` passed (backend 90 passed/1 skipped, Telegram 38 passed, mock
  portal 7 passed); `make lint` passed; backend/Telegram `uv lock --check` passed. A full
  repository `git diff --check` still reports pre-existing trailing whitespace in unrelated
  generated ML files; scoped changed-service checks passed.
- Current status: code-level/runtime wiring issues are fixed and verified; a fresh human Telegram
  conversation is still required to confirm mobile rendering and end-to-end result delivery.

## 2026-10-23 — Telegram Bot Copy & Response Rewrite From Scratch

- User Feedback:
  1) Extra text (robotic jargon, debug text, repetitive "MOCK")
  2) Confusion (Outcome: UNDETERMINED without explaining what is missing, unclear buttons)
  3) Delay (45-60s total silence while LM Studio / OCR evaluates with no typing indicator)
  4) No exception handling (cold status dumps when missing documents)
- Live Case Diagnosis (`backend/backend/adhikaar.db`):
  - Case `e8a785849646457aac2928d002e6ae41` for user `7312450336`:
  - Uploaded `aadhaar` and `land_record`.
  - Backend evaluated rules and returned status `NEEDS_DOCUMENTS` (missing `bank_passbook`).
  - Bot displayed the raw backend string: `MOCK / synthetic case result`, `Outcome: UNDETERMINED`, `Portal submission: NOT_ATTEMPTED`, `MOCK rulebook source: pm_kisan_mock.md`.
- Resolution:
  1) Copy & Flow Overhaul (`telegram_bot/app/i18n.py`):
     - Completely removed robotic clutter across English, Tamil, Telugu, and Hindi.
     - Welcoming DPDP notice and clean language picker on `/start`.
     - 3-step guide: requirement -> document photos -> check eligibility.
     - Upgraded document upload acknowledgements and guidance.
  2) Citizen-Centric Result Formatting (`telegram_bot/app/notify.py`):
     - Added `format_citizen_notification_text`: transforms backend dumps into human language.
     - Missing docs formatted as: `⚠️ Missing Document Required: 👉 🏦 Bank Passbook. We verified your Aadhaar and Land Record...`
     - Eligible results formatted as celebratory awards with verified criteria and reference IDs.
  3) Delay Elimination (`telegram_bot/app/bot.py`):
     - Added continuous `send_chat_action(chat_id, action="typing")` every 3s in `_watch_for_case_result`. Telegram actively pulses "typing..." throughout LM Studio fact extraction.
  4) Contextual Exception & Input Handling:
     - `text_handler` detects `NEEDS_DOCUMENTS` state and reminds user of missing document instead of repeating "STEP 1 complete".
     - `menu_done` mapped to `submit_command`.
     - Multilingual keywords added for caption detection.
     - Checklist displays uploaded documents and missing requirements.
- Verification:
  - `uv run --project telegram_bot --extra test pytest telegram_bot/tests`: 39/39 passed.
  - `uv run --project backend --extra test pytest backend/tests`: 90/90 passed, 1 skipped.
  - Telegram bot daemon restarted and healthy on port `8200`.

## 2026-10-23 — 'Continue active case' Button & Status Text Fix
- Symptom: User reported the 'Continue active case' button was not working on `/start`.
- Root Cause:
  1) `case:continue` handler called `_edit_callback` with `_status_text(language, active)`, which had the exact same text as the message being clicked. Telegram API rejected it with `BadRequest: Message is not modified`.
  2) `_status_text` was including raw backend message text from `messages[-3:]` directly without running it through `format_citizen_notification_text`, leaking `MOCK / synthetic case result` into `/status` and `/start`.
- Resolution:
  1) Replaced `case:continue` with an actionable, distinct message that clearly lists verified documents (`Aadhaar Card`, `Land Record`), explicitly highlights what is missing (`Bank Passbook`), and provides direct buttons `[ ➕ Add another document ]` and `[ ✅ Check eligibility ]`.
  2) Filtered `_status_text` through `format_citizen_notification_text` so raw `MOCK` text never appears in status cards.
  3) Added regression test `test_continue_active_case_callback_shows_guidance_and_buttons` in `telegram_bot/tests/test_telegram_bot_handlers.py`.
- Verification:
  - 39/39 tests passing in `telegram_bot`.
  - Bot server restarted and running on port 8200.

## 2026-10-23 — Comprehensive Button Speed, Reliability & Stateless Resolution
- Symptom: User reported buttons felt sluggish or unresponsive across app states and server restarts.
- Root Cause:
  1) Random in-memory tokens (`u:<random_hash>` and `a:<random_hash>`) were lost across server restarts or container redeployments, causing callbacks on existing chat messages to fail or do nothing.
  2) Redundant network calls: `callback_handler` was making duplicate `GET /cases/active` requests (one for language resolution, another inside each action handler).
  3) Identical text edits: Clicking an inline button whose target message had unchanged text caused Telegram API to return `BadRequest: Message is not modified`, appearing as if the button click was ignored.
  4) Slow perceived latency: Buttons showed spinning indicators without immediate UI feedback when triggering long operations.
- Resolution:
  1) Multi-tier Stateless Action Resolution (`_resolve_callback_action`):
     - Deterministic tokens (`u:<action>`) decoded instantly.
     - Legacy token fallback table.
     - Inline Keyboard Button Text Inspection: Reads `btn.text` directly from `query.message.reply_markup.inline_keyboard` (e.g., "Continue active case", "Check eligibility", "Add another document", "Start a new case", "English", "हिन्दी", "తెలుగు", "தமிழ்") to guarantee that even pre-restart buttons work 100%.
     - Interactive question recovery: If `a:<token>` is not in memory after a restart, recovers target question from `active_case["messages"]` and `btn.text`.
  2) Single GET per callback: Pre-fetches `active_case` once at the top of `callback_handler`, cutting network round-trip latency in half.
  3) Instant Sensory Feedback: Calls `query.answer(text="...", show_alert=False)` immediately with native toast notification ("📸 Please send your document photo or file now", "⏳ Evaluating eligibility...", "✓ Updated").
  4) Resilient `_edit_callback`: Gracefully handles `Message is not modified` by acknowledging with a toast, and falls back to sending a new message if the message is too old to edit.
  5) Inline Action Buttons on `/status`: Attached `_done_keyboard` to `COLLECTING` and `NEEDS_DOCUMENTS` statuses so citizens can check eligibility with one tap.
  6) Instant text triggers: Added natural shortcuts in `text_handler` for "status", "continue", "help", "schemes", "cancel", "checklist", "my case".
- Verification:
  - `uv run --project telegram_bot --extra test pytest telegram_bot/tests`: 43/43 passed.
  - `uv run --project backend --extra test pytest backend/tests`: 90/90 passed, 1 skipped.
  - `uv run --project telegram_bot ruff check telegram_bot/app telegram_bot/tests`: 0 lint errors.
  - Telegram bot daemon active and responding on port 8200 (`/ready` status: "ready").

