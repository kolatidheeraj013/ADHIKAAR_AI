# ADHIKAAR

ADHIKAAR is a mock, privacy-first welfare-entitlement agent. The implementation
specification in `implementation.md` is the single source of truth.

## Phase 0 scaffold

The repository is split into independently deployable concerns:

- `backend/` — FastAPI API service
- `telegram_bot/` — thin Telegram channel service
- `mock_portal/` — deterministic scheme-portal simulator
- `frontend/` — Next.js web fallback and reviewer UI
- `ml_training/`, `data/`, `scripts/`, `docs/` — offline assets and project tooling

### Local checks

```bash
make test
make lint
```

Docker is the intended local orchestration path:

```bash
docker compose up --build
```

Default health endpoints are:

- Backend: <http://localhost:8000/health>
- Mock portal: <http://localhost:8100/health>
- Telegram bot: <http://localhost:8200/health>
- Frontend: <http://localhost:3000>

Only synthetic data belongs in this repository. Never place real identity
documents, credentials, or personal data in source, fixtures, logs, or tests.

## Rulebook RAG (Phase 6)

The two rulebooks under `data/rulebooks/` are clearly labeled `MOCK` and are
used only for scheme discovery and explanation citations. Eligibility remains
authoritative in the deterministic YAML rules under
`backend/app/rules/schemes/`. Install the optional vector dependencies with
`pip install -e 'backend[rag]'`; when ChromaDB or a local sentence-transformers
model is unavailable, the same flow uses a deterministic lexical index and
persists it below `CHROMA_PATH` (default `./.chroma`).
