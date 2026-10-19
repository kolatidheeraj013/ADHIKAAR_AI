# ADHIKAAR Phase 1 Checkpoint

## Status

- Phase: 1 — Rules engine
- State: complete; waiting for CTO approval before Phase 2
- Source of truth: `implementation.md` §6 and §21

## Shipped

- Added Pydantic v2 scheme models and fail-fast YAML loading.
- Added `pm_kisan_mock.yaml` and `state_scholarship_mock.yaml`, with explicit MOCK
  labels, required documents, declaration questions, payload fields, and rules.
- Added a pure evaluator using `simpleeval`, with no `eval` or `exec`.
- Added tri-state outcomes and per-rule traces with fact keys, document provenance,
  and safe reasons.
- Rejected unsupported expression syntax, private names, undeclared facts, and
  non-boolean rule results.

## Decisions

- Scheme `source` values remain document identifiers such as `land_record` and
  `aadhaar`; only `declaration` has citizen-question semantics.
- Missing facts never pass. If any rule fails, the outcome is `NOT_ELIGIBLE`; otherwise
  missing facts produce `UNDETERMINED` before an all-pass result can be `ELIGIBLE`.
- The evaluator accepts plain fact values and future state-model fact objects/mappings,
  preserving `source_doc_id` without importing backend state models.

## Checks

- `make test` — passed: 19 tests across backend, Telegram, mock portal, and rules engine.
- `make lint` — passed: Ruff clean.
- `python -m compileall -q app/rules tests/test_rules_engine.py` — passed.
- `load_schemes()` smoke check — both MOCK schemes loaded.

## Risks

- Scheme facts are structurally validated, but runtime fact-type coercion remains a
  later integration concern when extraction/state models are wired in.
- Docker remains unavailable in this runner; service orchestration is still unverified.

## Exact next step

Wait for Dheeraj's `go`, then implement Phase 2 only: SQLAlchemy/Alembic models,
PII-safe append-only audit logging, local storage, and retention purge behavior.
