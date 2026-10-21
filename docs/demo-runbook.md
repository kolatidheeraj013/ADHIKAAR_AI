# ADHIKAAR Phase 10 Demo Runbook

This runbook is the cold-start path for the synthetic, privacy-safe demo. It does
not require cloud credentials, Docker, Telegram credentials, or real identity data
for the offline web/demo path.

## Cold start

From the repository root:

```bash
uv --version
make seed
make demo
```

`make seed` prints the deterministic scenario inventory. `make demo` runs scenarios
A, B, C, D1, D2, and E using the real LangGraph flow with local SQLite and fake
integrations. It should complete in well under five minutes and print one evidence
line per scenario.

Expected results:

- A: complete, high confidence, portal submission.
- B: missing-document state followed by document re-entry and completion.
- C: review-band confidence followed by reviewer approval.
- D1: targeted field extraction and a second portal attempt.
- D2: permanent portal rejection and review escalation.
- E: citizen question followed by a resumed completion.

All values and documents in this runner are synthetic. The LLM does not decide
eligibility; the deterministic rules engine does.

## Offline web path

Start the backend in offline mode:

```bash
set DEMO_MODE=offline
uv run --isolated --project backend python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another shell, start the frontend:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open `http://localhost:3000`, accept consent, use synthetic text such as
`farmer PM-Kisan nobody pays tax`, and upload synthetic sample images only. The
reviewer flow uses the configured reviewer token and is intended for the blurry and
portal-recovery scenarios.

## Telegram path

Telegram requires internet and a local BotFather token. Keep the token only in the
local runtime environment; never paste it into chat, source, tests, logs, or Git.
Follow the Telegram setup in `README.md`, then test `/start`, language, consent,
synthetic text/voice, synthetic image uploads, Done, and `/status`. The backend may
remain in `DEMO_MODE=offline`: that mode keeps business integrations deterministic,
but Telegram cases still receive the internal notifier's questions and final result.

## Cleanup

The offline script uses temporary SQLite state and removes it after each scenario.
For a running backend, use the existing data-retention/purge tooling:

```bash
uv run --isolated --project backend python scripts/purge.py
```
