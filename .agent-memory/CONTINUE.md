# ADHIKAAR Continuation Checkpoint

- Objective: Telegram Bot Final Refinements & Graceful Offline Fallback (`v5.2-Telegram-final refienments`).
- Completed Deliverables:
  1. Telegram UI & Menu Polish:
     - Fixed active case replacement prompt button label: replaced truncated long prompt string with clean action buttons `[🗑️ Delete & Start New]` and `[Keep Active Case]` across English, Tamil, Telugu, and Hindi.
     - Removed intrusive persistent bottom reply keyboard buttons `[📋 What I uploaded]` and `[❌ Cancel application]` that were sticking to the screen after starting chat; restored standard persistent menu (`Start new application`, `Continue / status`, `Browse schemes`, `Help`, `Delete data`, `Language / privacy`).
     - Kept checklist and cancellation actions available via slash commands (`/checklist`, `/cancel`) and inline keyboards.
  2. Timezone-Aware 1-Hour Case Expiry:
     - Fixed SQLite naive datetime parsing in `_active_case` (`telegram_bot/app/bot.py`) and `active_case` (`backend/app/main.py`) by explicitly normalizing with `.replace(tzinfo=UTC)`, resolving `TypeError` that previously broke the 1-hour auto-expiration.
  3. Resilient LLM Fallback:
     - Added automatic fallback to heuristic/fixture extraction in `ProviderLLMClient.extract_facts` (`backend/app/integrations/llm.py`) when live LLM connection is closed/unreachable, allowing the app to keep working seamlessly even when LM Studio is stopped.
  4. Test & Quality Verification:
     - 55/55 Telegram bot tests passing, 92/92 Backend tests passing, 7/7 Mock Portal tests passing, 0 Ruff lint errors.
- Files to inspect first: this file, `telegram_bot/app/bot.py`, `telegram_bot/app/i18n.py`, `backend/app/integrations/llm.py`, `backend/app/main.py`.

- Phase 4 outcome:
  - `backend/app/integrations/sarvam.py`: ffmpeg 16 kHz mono WAV normalization, duration validation (<=30s), language mapping (`ta|te|hi|en` -> `ta-IN|te-IN|hi-IN|en-IN`), live translation/STT, and offline fixture fallback.
  - `backend/app/integrations/ocr.py`: PaddleOCR wrapper with angle classification, confidence scoring, and offline fixture fallback.
  - `backend/app/integrations/llm.py`: Provider-agnostic OpenAI-compatible `/chat/completions` client supporting any provider/base URL, Pydantic-validated JSON extraction, single-field targeted re-extraction for portal recovery (`extract_field`), 1-retry on malformed JSON, PII masking (`mask_identifiers`), and explanation generation aligned with decision outcomes.
  - `data/fixtures/`: Recorded voice transcripts, OCR results, and LLM fact extractions for offline demo/test mode.
- Tests verified: 53 passed across services (51 backend, 1 telegram_bot, 1 mock_portal) via isolated `uv run` environments; `ruff check` passed cleanly.
- Phase 5 outcome: synthetic watermarked document generator, quality degradations,
  dual-head ResNet18-style model, training/evaluation entry points, and heuristic/model
  `DocumentClassifier` implementing the existing `DocClassifier` protocol.
- Phase 5 tests: 55 backend tests passed, with 1 optional model-shape test skipped because
  PyTorch is unavailable; `make test` also passed the Telegram and mock-portal tests.
- Hugging Face note: the fine-tuned Llama 3.1 8B model will be imported/deployed later
  through the existing OpenAI-compatible `LLM_BASE_URL` boundary. Do not block Phase 7
  on the model artifact.
- Phase 6 outcome: MOCK rulebooks, heading-based chunks, ChromaDB/local embedding path,
  persisted lexical fallback, scheme discovery in `plan`, and source citations in
  `explain`. RAG is informational only; the rules engine still decides eligibility.
- Phase 6 tests: 6 focused tests; full backend suite 61 passed, 1 optional skipped.
- Phase 7 outcome: HTTP `PortalClient` with structured timeout/transient/validation/
  permanent errors; mock portal application, verification, and dev failure-mode
  endpoints; portal audit events; two transient retries; one targeted field recovery;
  permanent/exhausted recovery escalation with masked evidence.
- Phase 7 tests: focused backend/recovery tests 12 passed; mock portal tests 6 passed
  under system pytest because the mock portal uv environment has a broken Pygments
  install; full `make test` passed with 65 backend tests, 1 optional skip, 1 Telegram
  test, and 7 mock-portal tests.
- Phase 8 outcome: FastAPI case lifecycle and reviewer/audit API, service/reviewer
  auth, sanitized SSE, delete/purge behavior, voice validation/storage, missing-doc
  re-entry, and `NoopNotifier`; Next.js citizen intake with consent-first uploads,
  optional MediaRecorder voice, live case updates, question/document recovery,
  reviewer evidence/actions, masked identifiers, and audit timeline.
- Phase 8 tests: `make test` passed with 73 backend tests, 1 optional skip, 1 Telegram
  test, and 7 mock-portal tests; `make lint`, `npx tsc --noEmit`, `uv lock --check`,
  and scoped `git diff --check` passed. `npm run build` compiled and generated all
  pages but exceeded the five-minute runner limit while collecting standalone build
  traces; no TypeScript/build errors were reported before timeout.
- Phase 9 outcome: real async PTB v21 bot, polling/webhook lifecycle, authenticated
  backend notification path, TelegramNotifier with bounded retries, onboarding/media/
  command/callback handlers, album debounce, i18n, and test fakes. The bot now also
  has a persistent localized menu, `/new`, `/schemes`, `/language`, safe active-case
  replacement confirmation, backend-driven MOCK scheme browsing, richer document
  guidance, and explicit no-bot-side-eligibility wording.
- Phase 9 tests: `make test` previously passed with 75 backend tests, 1 optional skip,
  19 Telegram tests, and 7 mock-portal tests; the focused Telegram suite currently
  passes 19 tests, direct Ruff passes, compileall and diff checks pass, and both lock
  files validate. Live Telegram smoke test remains open.
- Phase 10 outcome: `backend/app/demo.py` and `scripts/run_demo.py` run deterministic
  synthetic scenarios A/B/C/D1/D2/E through the real graph; `scripts/seed.py` prints
  the seed inventory; Makefile checks use isolated uv environments; README, demo
  runbook, deployment notes, and final threshold measurements are documented.
- Phase 10 verification: backend 83 passed/1 skipped, Telegram 19 passed, mock portal
  7 passed, Ruff passed, compileall and scoped diff checks passed. GNU Make was later
  installed through WinGet; the direct Make targets can now run after a shell/app PATH
  refresh. Frontend build could not execute because `frontend/node_modules` is absent.
- Latest result/notification fix: Telegram cases use `TelegramNotifier` even when
  `DEMO_MODE=offline`; review entry now sends a citizen-facing result update; final
  results show scheme, deterministic outcome, case status, confidence band, rule
  reasons, MOCK benefit, portal state/reference, and next step.
- Latest result-fix verification: backend `86 passed, 1 skipped`, Telegram `19 passed`,
  mock portal `7 passed`, Ruff, compileall, and scoped diff checks passed. That check was
  recorded before GNU Make was installed; the later full Makefile run passed as documented
  below. Human Telegram re-test remains pending.
- Latest user-flow/model work: Telegram now treats a typed `Done`/localized Done label
  as the start action instead of forwarding it as citizen text. The backend can now
  select a configured OpenAI-compatible local LLM endpoint for fact extraction and
  targeted re-extraction; without `LLM_BASE_URL`, deterministic offline extraction is
  preserved. The attached `FT-backend.md` is currently empty, so this wiring follows
  the existing `ProviderLLMClient` interface rather than an external plan.
- Earlier LM Studio connectivity was refused before the local server was started; that
  diagnosis is superseded by the live verification below.

- Live LM Studio integration is VERIFIED and OPERATIONAL:
  - Model: `dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF` (served as `adhikaar-llama3.1-8b-fact-extractor` on `http://127.0.0.1:1234/v1`).
  - Active configuration loaded via `.env` / `.env.local` (`LLM_PROVIDER=lmstudio`, `DEMO_MODE=live`).
  - `ProviderLLMClient` handles LM Studio response formats cleanly. Live smoke extraction succeeded on Aadhaar documents and targeted IFSC re-extraction.
  - Zero-network test invariant preserved via `conftest.py` setting `DEMO_MODE=offline`. Full backend suite passes (89 passed, 1 skipped).
  - Decision D-013 recorded in `DECISIONS.md`.

- Telegram Bot Overhaul & Outcome Pipeline Repair (2026-10-21):
  - Fixed root cause of cases stuck in `COLLECTING` (case-insensitive & multilingual `done_triggers`, persistent `[ ✅ Submit / Done ]` menu button).
  - Fixed root cause of missing outcomes after photo upload (sequential fallback for unclassified `"other"` photos, `doc_type` parameter in `/documents`, caption/filename detection, interactive tagging keyboard).
  - Replaced silent photo deletion with DPDP privacy reassurance message.
  - Added `/checklist` command and dynamic `ReplyKeyboardMarkup` state-switching.
   - Full suite verified: `telegram_bot` (28 passed), `backend` (89 passed, 1 skipped).

- Telegram UX v3 (2026-10-23):
  - Rebuilt the visible flow around explicit steps and one primary action: `Check eligibility`.
  - Upload acknowledgements now offer `Add another document` or `Check eligibility`; the
    persistent keyboard is limited to `What I uploaded` and `Cancel application` while collecting.
  - Added `/submit`, `/cancel`, terminal `/status` recovery through `/cases/latest`, and a
    persisted-case result watcher to recover missing/delayed push notifications.
  - Same bot identity/token boundary retained; no token was read or stored in memory.
- Verification: `make test` passed with backend 90 passed/1 skipped, Telegram 31 passed,
  mock portal 7 passed; `make lint`, compileall, and diff checks passed.

- Telegram reliability debugging (2026-10-23):
  - Confirmed the current runner's default ports 8000/8200 were not listening; isolated
    services had been started on 18000/18200 instead. Bot API `getMe` still succeeds for
    `@Adhikaar013bot`, with no webhook and zero pending updates.
  - Fixed the consent callback's invalid `ReplyKeyboardMarkup` edit, `/submit` error path,
    result fallback after answering a question, restart recovery for pending question buttons,
    duplicate notification race, cross-chat answer callbacks, locale key parity, and runtime
    service configuration.
  - Added `/ready` and explicit Compose service URLs; declared `python-dotenv` dependencies.
  - Verification: backend 90 passed/1 skipped, Telegram 38 passed, mock portal 7 passed,
    `make lint` passed, `uv lock --check` passed for backend and Telegram.

## Exact first action for the next coding session
 
Proceed with Telegram commands refinement: review and polish all citizen commands (`/start`, `/schemes`, `/checklist`, `/status`, `/help`, `/new`, `/language`, `/cancel`), ensuring immediate sub-second feedback, streamlined menus, mobile UX clarity, and natural vernacular copy across English, Hindi, Tamil, and Telugu.

