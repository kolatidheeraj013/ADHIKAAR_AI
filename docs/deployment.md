# ADHIKAAR Deployment Notes

## Local services

The compose file defines PostgreSQL, backend, mock portal, Telegram, and frontend.
Before a real deployment, provide an environment file with service tokens, database
URL, reviewer password, and (only for Telegram) the BotFather token. Keep secrets
outside Git and outside logs.

```bash
docker compose config
docker compose up --build
```

Health endpoints:

- Backend: `http://localhost:8000/health`
- Mock portal: `http://localhost:8100/health`
- Telegram bot: `http://localhost:8200/health`
- Frontend: `http://localhost:3000`

## Offline versus live mode

- `DEMO_MODE=offline` uses deterministic local fixtures/fakes for business integrations.
  Telegram cases still use the internal notifier so citizens receive questions and
  final results; this mode does not disable Telegram delivery.
- Live backend integrations must be configured behind their existing Protocol
  boundaries and must not move eligibility decisions into an LLM.
- To opt into local LM Studio fact extraction, configure the backend with:

  ```text
  LLM_PROVIDER=lm_studio
  LLM_BASE_URL=http://127.0.0.1:1234/v1
  LLM_MODEL=dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF
  LLM_API_KEY=
  ```

  `LLM_BASE_URL` is the opt-in switch. It uses the OpenAI-compatible
  `/v1/chat/completions` endpoint for fact extraction and targeted field
  re-extraction. When it is unset, fact extraction remains deterministic and
  offline; no local LM Studio secret is required.
- Telegram polling is suitable for local development. Production Telegram uses
  webhook mode with `TELEGRAM_WEBHOOK_URL` and `TELEGRAM_WEBHOOK_SECRET`.

## Persistence and operations

- Use PostgreSQL and a persistent storage volume for deployed cases.
- Run database migrations before serving traffic.
- Keep uploaded documents private and apply the configured retention policy.
- Monitor all `/health` endpoints before opening the frontend or Telegram channel.
- Do not expose reviewer or service tokens to the browser or Telegram chat.

Docker is not available in the current development runner, so the compose deployment
path is documented but not claimed as locally executed here.
