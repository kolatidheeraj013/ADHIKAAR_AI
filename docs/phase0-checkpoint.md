# ADHIKAAR Phase 0 Checkpoint

## Status

- Phase: 0 — Scaffold
- State: complete; waiting for CTO approval before Phase 1
- Source of truth: `implementation.md`

## Shipped

- Created the service-owned repository layout from implementation.md §4.
- Added FastAPI liveness endpoints for `backend`, `mock_portal`, and `telegram_bot`.
- Added a minimal Next.js + TypeScript + Tailwind frontend skeleton.
- Added service manifests, Dockerfiles, docker-compose orchestration, `.env.example`,
  Makefile, Ruff configuration, and synthetic-data guardrails.
- Added one health test per Python service.

## Decisions

- No business logic was added in Phase 0.
- Service boundaries are preserved: frontend and Telegram bot will use backend HTTP;
  no cross-service Python imports exist.
- `DEMO_MODE=offline` is the safe example default; secrets remain environment-only.
- Docker remains the intended orchestration path, but this runner has no Docker binary.
- The `/persistent-project-memory` capability is unavailable in this runtime. This
  redacted checkpoint is the fallback; it contains no credentials or real PII.

## Checks

- `make test` — passed: 3 service tests, one per service.
- `make lint` — passed: Ruff clean.
- `python -m compileall -q backend/app telegram_bot/app mock_portal/app ml_training scripts` — passed.
- FastAPI TestClient smoke check — all three `/health` endpoints returned 200 and the expected body.
- `npm run build` in `frontend/` — passed.
- `docker compose config` / `docker compose up` — not run; Docker is unavailable in the runner.

## Risks

- Docker health and inter-service startup are unverified until a Docker-capable environment is used.
- Frontend install reported 9 npm audit findings (3 moderate, 6 high); remediation is out of Phase 0 scope.
- FastAPI's current TestClient emitted a Starlette/httpx deprecation warning; tests still pass.

## Exact next step

Wait for Dheeraj's `go`, then implement Phase 1 only: Pydantic-validated MOCK YAML
schemes, the `simpleeval` tri-state rules engine, and table-driven tests including
missing-fact and injected-code rejection.
