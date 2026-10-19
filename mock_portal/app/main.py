from fastapi import FastAPI

app = FastAPI(title="ADHIKAAR Mock Portal", version="0.1.0")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a stable liveness response for local orchestration."""
    return {"service": "mock_portal", "status": "ok"}
