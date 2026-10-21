# ADHIKAAR Project Memory

## Purpose

ADHIKAAR is a synthetic-data-only welfare-entitlement agent. The LLM extracts
and explains; deterministic rules decide; humans handle doubt. The authoritative
specification is `implementation.md`.

## Confirmed stack and layout

- Backend: FastAPI, Python 3.11+, Pydantic v2, SQLAlchemy/Alembic planned.
- Agent: LangGraph planned for Phase 3; integrations must use Protocols and fakes.
- Frontend: Next.js App Router, TypeScript, Tailwind.
- Services: `backend/`, `telegram_bot/`, `mock_portal/`, `frontend/`, plus
  `ml_training/`, `data/`, `scripts/`, and `docs/`.
- Folder boundary: frontend/Telegram use backend HTTP; backend uses interfaces for
  bot and portal; no cross-service Python imports.

## Verified completed work

- Phase 0: service scaffold, health endpoints, Next.js skeleton, compose/env/Makefile,
  tests and lint configuration.
- Phase 1: Pydantic-validated MOCK YAML schemes and pure `simpleeval` tri-state
  rules engine with per-rule trace and malicious-expression rejection.
- Phase 1 checks: `make test` 19 passed; `make lint` passed; compileall passed.
- Phase 2: SQLAlchemy models/Alembic baseline, append-only PII-safe audit, local
  storage, retention purge; 26 repo tests passed.
- Phase 3: LangGraph fake-backed walking skeleton with interrupts, SQLite checkpoint
  helper, routing/recovery, and scenarios A/B/C/D1/D2/E; 34 repo tests passed.
- Phase 4: Concrete Speech (`SarvamSpeechClient` with ffmpeg normalization and <=30s validation),
  OCR (`PaddleOCRClient` with angle cls and confidence scoring), and LLM (`ProviderLLMClient`
  with OpenAI-compatible endpoint, Pydantic validation, single-field targeted re-extraction,
  and PII masking). Recorded offline fixtures in `data/fixtures/`. 53 repo tests passed.
- Phase 5: Synthetic document dataset generator, dual-head ResNet18-style model,
  local training/evaluation entry points, and `DocumentClassifier` inference with
  deterministic fallback. Phase 5 tests pass; PyTorch is optional and unavailable in
  the current runner, so the model-shape test is skipped and training reports fallback.
- Phase 6: MOCK markdown rulebooks, heading-based ingestion, ChromaDB/local
  sentence-transformers integration when locally available, persisted lexical fallback,
  scheme discovery, and explanation citations. RAG tests pass and rules remain separate.
- Phase 7: HTTP `PortalClient`, deterministic mock portal application/verification
  endpoints, required-field validation, timeout/permanent failure modes, portal audit
  events, bounded transient retry, targeted field recovery, and escalation evidence.
  Phase 7 and full repository tests pass.
 - Phase 8: FastAPI citizen case lifecycle, service-token active-case lookup,
  consent/upload validation, voice and document persistence, graph start/resume,
  sanitized SSE, delete-my-data redaction/purge, reviewer queue/evidence/resume/audit,
  and `NoopNotifier`; Next.js citizen intake, case recovery, reviewer, and audit pages.
   API tests, full repository tests, Ruff, and TypeScript checks pass.
  - Phase 9: Real `python-telegram-bot` v21 async service with polling/webhook
    lifecycle, language/consent onboarding, text/voice/photo/image-document forwarding,
    album debounce, bounded callbacks, `/status`, `/delete`, `/help`, authenticated
    internal notifications, i18n, and backend `TelegramNotifier` delivery retries.
    The citizen UX also includes a persistent localized menu, `/new`, `/schemes`,
    `/language`, safe active-case replacement confirmation, backend-driven MOCK scheme
    browsing, document guidance, and explicit separation between bot presentation and
    backend eligibility decisions. Offline tests and lint pass; human chat acceptance
    is pending.

## Current continuation focus

  - Phases 0–9 are implemented; Phase 9 offline behavior is verified and Bot API
    connectivity is verified for `@Adhikaar013bot` without exposing the token.
  - Current checkpoint: Phase 10 is offline-verified; live Telegram chat smoke test is
    pending because the agent cannot act as the user's Telegram account.
  - The deterministic demo runner and runbook are now the cold-start path.
- Colab fine-tuning for Llama-3.1-8B runs asynchronously; model will plug directly into
  `ProviderLLMClient` via `LLM_BASE_URL` without backend code changes (D-009).
- `SARVAM_API_KEY` is present in local environment; falls back cleanly to offline fixtures if unset.
- Fine-tuned Llama 3.1 8B is planned for later Hugging Face import/deployment through
  the OpenAI-compatible `LLM_BASE_URL`; it is not required to pass Phase 4 or Phase 5.

## Safety constraints & decisions

- Data & privacy resolution (D-007): Real documents uploaded at runtime by citizens
  are supported with ephemeral private storage (`RETENTION_DAYS=7`), in-memory OCR/LLM
  extraction, and PII masking. Classifier training remains strictly synthetic-with-augmentation
  with `SAMPLE — NOT A REAL DOCUMENT` watermark to comply with Aadhaar Act §29 and DPDP Act.
- Audit evidence is append-only and PII-safe; raw 12-digit citizen identifiers are masked.
- Rules engine is deterministic; LLM extracts and explains; no model decides eligibility.

## Environment gaps

- Docker is not installed in the current runner, so compose startup is unverified.
- All services verified via isolated project `uv run` virtual environments.
- GNU Make was initially absent from the Windows shell. It is now installed through
  WinGet (`ezwinports.make` 4.4.1); existing shells need a PATH refresh before plain
  `make test`/`make lint` resolve it.
- The existing `backend/.venv` is incomplete/locked on this runner; the backend was
  started successfully with `uv run --isolated --project backend ...`. This is an
  environment issue, not an application failure.
- `/persistent-project-memory` extension was unavailable; these Markdown files are
  the durable project-memory fallback.
- Phase 3 uses `langgraph` with the compatible `langgraph-checkpoint-sqlite` 2.x
  adapter for local durable resumes.
- `graphify-out/graph.json` exists and the graphify report has previously been
  refreshed; use graphify's existing-graph query path for future codebase questions
  instead of rebuilding unless an explicit update/rebuild is requested.
- Graphify was incrementally refreshed with `--update --code-only` and `cluster-only`:
  graph output is now 1160 nodes, 2837 edges, and 62 communities in `graphify-out/`.
  Non-code semantic files were intentionally not re-extracted because no graphify-supported semantic API key was available.

## Phase 10 demo assets

- `backend/app/demo.py` runs the real graph with deterministic fakes for scenarios
  A/B/C/D1/D2/E and returns sanitized acceptance evidence.
- `scripts/seed.py` prints the synthetic seed inventory; `scripts/run_demo.py` runs one
  scenario or all scenarios.
- `docs/demo-runbook.md` documents cold start, offline web, Telegram, and cleanup.
- `docs/deployment.md` documents compose health, migration, persistence, secrets, and
  polling/webhook operations.
- `docs/confidence-thresholds.md` records measured Phase 10 confidence outputs.

## Telegram result delivery and UX modernization

- Telegram cases select `TelegramNotifier` for push delivery to citizen chats.
- Streamlined dynamic reply keyboard: active collection displays only `[ ✅ Submit / Done ]` and `[ ❌ Cancel Case ]`; active questions/processing displays only `[ ❌ Cancel Case ]`. Idle states provide localized menu options without cluttering mobile screens.
- Restart recovery in `backend/app/main.py`: allows un-resumable cases with no active in-memory run to restart cleanly rather than throwing 409 Conflict.
- Result text includes the scheme, deterministic outcome, case status, evidence confidence band, rule reasons, MOCK benefit, portal state/reference, and next step.

## Local LM Studio fact extractor (Live Verified)

- `ProviderLLMClient` wired to local LM Studio endpoint `http://127.0.0.1:1234/v1` serving model `adhikaar-llama3.1-8b-fact-extractor`.
- Live Pydantic-validated JSON fact extraction and targeted `extract_field` verified against actual local LLM.
- Real Telegram case `2c19f77c` extracted facts, asked qualification question, received `No`, evaluated to `ELIGIBLE` under PM-Kisan, and auto-submitted to mock portal (`MOCK-PORTAL-001`).

## Frontend & ML Classifier Status

- Frontend: Next.js 15 App Router, TypeScript, Tailwind production build (`npm run build`) verified cleanly for all 5 static/dynamic routes.
- Classifier: `DualHeadResNet18` trained for 5 epochs on synthetic documents (`ml_training/weights/doc_classifier.pt`, 44.8 MB) and evaluated via `ml_training/evaluate.py`.
- Release: Commit `v1` pushed to GitHub (`main -> origin/main`). Zero regressions across all 124 tests and `make lint`.
