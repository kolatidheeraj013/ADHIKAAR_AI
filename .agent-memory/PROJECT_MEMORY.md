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

## Safety constraints

- Synthetic documents and identifiers only. No real PII, credentials, or API keys
  in source, logs, fixtures, prompts, tests, or memory.
- Audit evidence must be PII-safe and append-only. Missing eligibility facts never pass.
- Do not fabricate official scheme rules; current scheme rules are explicitly MOCK.

## Environment gaps

- Docker is not installed in the current runner, so compose startup is unverified.
- `/persistent-project-memory` extension was unavailable; these Markdown files are
  the durable project-memory fallback.
- Phase 3 uses `langgraph` with the compatible `langgraph-checkpoint-sqlite` 2.x
  adapter for local durable resumes.
