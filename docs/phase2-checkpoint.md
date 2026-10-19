# ADHIKAAR Phase 2 Checkpoint

## Status

- Phase: 2 — DB, audit, storage
- State: complete; Phase 3 authorized in the current user request
- Source of truth: `implementation.md` §§5, 17, 21

## Shipped

- Added SQLAlchemy 2 models for all eight domain tables plus UUID4 keys and timestamps.
- Added SQLite/Postgres-compatible engine/session helpers and an Alembic baseline.
- Added PII-safe `audit.log()` and node decorator; raw OCR and long identifiers are
  redacted, while masked last-four values remain usable.
- Enforced audit append-only behavior with ORM listeners and SQLite database triggers.
- Added `StorageBackend` protocol, private local storage with traversal protection,
  and `purge_expired()` that removes old files but retains document metadata.

## Checks

- `make test` — passed: 26 tests; one existing Starlette/httpx deprecation warning.
- Phase 2 focused tests — passed: 7 tests.
- `make lint` plus `ruff check scripts/purge.py` — passed.
- `alembic -c backend/alembic.ini upgrade head` — passed on SQLite.
- `alembic -c backend/alembic.ini check` — passed with no pending operations.
- `python -m compileall -q backend/app scripts` — passed.

## Risks

- Docker/Postgres runtime is not available in this runner; only SQLite migration and
  behavior are verified locally.
- Production storage and database adapters are still intentionally absent.

## Exact next step

Implement Phase 3 only: typed `CaseState`, integration protocols/fakes, audited
LangGraph nodes, routing, resumable checkpoints, and the six fake-backed scenarios.
