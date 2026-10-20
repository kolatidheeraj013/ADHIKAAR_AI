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
