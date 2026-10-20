# ADHIKAAR Continuation Checkpoint

- Objective: Advance ADHIKAAR per `implementation.md` into Phase 9 (Telegram bot).
- Completed: Phases 0–8 are implemented; Phase 8 API behavior is verified.
- Active checkpoint: Phase 8 complete except the standalone Next.js build command
  exceeded the five-minute runner limit during final output-file tracing. TypeScript
  checking, Next compilation/page generation, API tests, full repository tests, and
  Ruff passed.
- Files to inspect first: this file, `implementation.md` §§15, 18, 19, and 21,
  `telegram_bot/`, `backend/app/integrations/notifier.py`,
  `backend/app/main.py`, and the Phase 8 API tests.
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

## Exact first action for the next coding session

Begin Phase 9 only after resolving or accepting the frontend build-trace timeout:
read `implementation.md` §§15, 18, 19, and 21; inspect `telegram_bot/`, backend
notifier integration, and the Phase 8 API contract. Implement thin-client onboarding,
voice/text/photo handlers, album debounce, `/internal/notify`, inline-keyboard
questions, `/status`, `/delete`, i18n, service-token enforcement, and handler tests.
Do not add eligibility/OCR/LLM/business logic to the bot.
