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
