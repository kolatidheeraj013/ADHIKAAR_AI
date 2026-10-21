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

### Phase 10 demo

The deterministic Phase 10 demo is synthetic-only and runs without cloud credentials:

```bash
make seed
make demo
```

See [`docs/demo-runbook.md`](docs/demo-runbook.md) for the offline web flow and
[`docs/deployment.md`](docs/deployment.md) for deployment notes. The demo runner
covers scenarios A, B, C, D1, D2, and E using the real graph with local fake-backed
integrations. It does not claim official welfare-program rules.

Docker is the intended local orchestration path:

```bash
docker compose up --build
```

Default health endpoints are:

- Backend: <http://localhost:8000/health>
- Mock portal: <http://localhost:8100/health>
- Telegram bot: <http://localhost:8200/health>
- Frontend: <http://localhost:3000>

### Real Telegram bot

The Telegram service is a real `python-telegram-bot` v21 application. It is not a
simulator: in polling mode it connects to Telegram's Bot API, receives real user
messages, downloads real voice/photo uploads, forwards them to the backend, and sends
backend notifications back to the same chat.

Never paste the bot token into chat, source files, tests, logs, or Git. Put the token
from BotFather in a local environment variable or an untracked `.env` file:

```bash
cd telegram_bot
export TELEGRAM_BOT_TOKEN='replace-locally-only'
export TELEGRAM_MODE=polling
export BACKEND_URL=http://127.0.0.1:8000
export SERVICE_TOKEN=change-me
uv run uvicorn app.main:app --host 0.0.0.0 --port 8200
```

Start the backend with the same `SERVICE_TOKEN` and `BOT_INTERNAL_URL`. Telegram
cases use the internal Telegram notifier even when `DEMO_MODE=offline`; offline mode
only selects deterministic business integrations and does not suppress the user's
Telegram result messages. Use `DEMO_MODE=live` only when you intentionally want live
external business integrations. The bot token is read only by `telegram_bot/`; the
backend never receives it. Polling is for local/dev use. Production webhook mode
additionally requires `TELEGRAM_WEBHOOK_URL` and `TELEGRAM_WEBHOOK_SECRET`.

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

## Local LM Studio fact extraction

The backend can use a locally served OpenAI-compatible LM Studio model for fact
extraction and targeted portal-recovery re-extraction. Set these variables in the
backend process environment:

```bash
LLM_PROVIDER=lm_studio
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_MODEL=dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF
LLM_API_KEY=
```

`LLM_BASE_URL` is the opt-in switch. The backend calls
`/v1/chat/completions` and LM Studio does not require `LLM_API_KEY`; leave it
empty for local use. If `LLM_BASE_URL` is unset, the backend keeps its
deterministic offline fact extraction behavior. The model only extracts facts or
formats explanations: eligibility remains deterministic in the rules engine.
