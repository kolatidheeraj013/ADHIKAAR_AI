# ADHIKAAR Decisions

## D-001 — deterministic eligibility

- Date: 2026-10-19
- Decision: Eligibility is decided only by the pure YAML + `simpleeval` rules engine.
- Reason: Required by `implementation.md`; prevents LLM eligibility hallucinations.
- Related files: `backend/app/rules/engine.py`, `backend/app/rules/schemes/`.
- Status: accepted.

## D-002 — local memory fallback

- Date: 2026-10-19
- Decision: Use `.agent-memory/` Markdown because the requested persistent-memory
  extension is not available in this runtime.
- Reason: Preserve resumability without storing secrets or inventing history.
- Status: active until the extension is available.

## D-003 — two-phase authorization

- Date: 2026-10-19
- Decision: User authorized Phases 2 and 3 in this turn; no later phase starts here.
- Reason: The implementation plan requires phase gates, while the latest request
  explicitly grants the next two phases.
- Status: active for this session.

## D-004 — audit enforcement layers

- Date: 2026-10-19
- Decision: Protect `audit_events` with both SQLAlchemy ORM listeners and SQLite
  database triggers; preserve audit rows during retention purge.
- Reason: The spec requires append-only behavior and the local demo uses SQLite.
- Related files: `backend/app/audit.py`, `backend/app/db/session.py`, `backend/app/db/models.py`.
- Status: accepted.

## D-005 — Phase 3 local checkpoint

- Date: 2026-10-19
- Decision: Use LangGraph's SQLite checkpoint adapter for local resumability and
  deterministic fakes for every external integration.
- Reason: Satisfies the walking-skeleton resume requirement without network calls or
  provider credentials; production checkpointer/provider wiring remains later work.
- Related files: `backend/app/agents/graph.py`, `backend/app/integrations/fakes.py`.
- Status: accepted for the MVP skeleton.
