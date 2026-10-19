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
