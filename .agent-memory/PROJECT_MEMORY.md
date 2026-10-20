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

## Current continuation focus

- Phases 0–5 are complete and verified.
- Next phase: Phase 6 (RAG: rulebook ingestion and retriever for scheme discovery and
  explanation citations; never eligibility decisions).
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
- `/persistent-project-memory` extension was unavailable; these Markdown files are
  the durable project-memory fallback.
- Phase 3 uses `langgraph` with the compatible `langgraph-checkpoint-sqlite` 2.x
  adapter for local durable resumes.
- `graphify-out/graph.json` exists and the graphify report has previously been
  refreshed; use graphify's existing-graph query path for future codebase questions
  instead of rebuilding unless an explicit update/rebuild is requested.
- Graphify was incrementally refreshed after Phase 5 with `--code-only`; current graph
  output is 653 nodes, 1303 edges, and 63 communities. Non-code semantic files were
  intentionally not re-extracted because no graphify-supported semantic API key was
  available.
