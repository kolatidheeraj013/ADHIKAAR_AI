from fastapi import FastAPI

app = FastAPI(title="ADHIKAAR Telegram Bot", version="0.1.0")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a stable liveness response for local orchestration."""
    return {"service": "telegram_bot", "status": "ok"}
