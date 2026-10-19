# ADHIKAAR Phase 3 Checkpoint

## Status

- Phase: 3 — agent graph with fakes
- State: complete; stop before Phase 4
- Source of truth: `implementation.md` §§7–10, 20–21

## Shipped

- Added typed Pydantic `CaseState` and records for facts, documents, decisions,
  questions, escalations, applications, and citizen messages.
- Added Protocols and deterministic fakes for speech, classification, OCR, LLM,
  retrieval, portal, notifier, and storage boundaries.
- Added dependency-injected LangGraph nodes for intake, transcription, document
  processing, planning, checks, eligibility, clarification, confidence, acting,
  verification, recovery, escalation, and explanation.
- Added real `interrupt()` / `Command(resume=...)` pauses for citizen questions and
  reviewer decisions, plus a persistent SQLite checkpointer helper.
- Enforced the hard rules: only ELIGIBLE reaches `act`; missing facts never pass;
  questions max at three; re-upload requests are bounded; portal retries max at two.

## Checks

- `make test` — passed: 34 tests; one LangGraph pending-deprecation warning.
- Phase 3 scenario tests — passed: A, B, C, D1, D2 permanent, D2 timeout, E, and
  SQLite checkpointer rebuild.
- `make lint`, `ruff check scripts/purge.py`, and compileall — passed.
- No real network calls or credentials used.

## Risks

- Graph nodes are centralized in `backend/app/agents/graph.py`; the spec's future
  one-file-per-node layout remains a refactor target, not a behavior gap for Phase 3.
- Real Sarvam/OCR/LLM/portal integrations are deliberately deferred to Phase 4/7.
- Docker remains unavailable in this runner.

## Exact next step

Stop and wait for Dheeraj's next authorization. Phase 4 will require external
provider decisions and credentials: Sarvam API key, LLM provider/key/model, and
validated OCR runtime/model availability.
