"""Deterministic in-memory scheme portal used by Phase 7 demos and tests."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="ADHIKAAR Mock Portal", version="0.1.0")

_FAIL_MODES = {"none", "timeout", "reject_permanent"}
_fail_mode = "none"
_applications: dict[str, dict[str, Any]] = {}
_next_reference = 1
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "pm_kisan_mock": ("applicant_name", "aadhaar_last4", "bank_account_number", "bank_ifsc"),
    "state_scholarship_mock": (
        "applicant_name",
        "aadhaar_last4",
        "bank_account_number",
        "bank_ifsc",
    ),
}


class ApplicationRequest(BaseModel):
    scheme_id: str = Field(min_length=1)
    payload_fields: dict[str, Any] = Field(default_factory=dict)


class DevConfigRequest(BaseModel):
    fail_mode: str


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return a stable liveness response for local orchestration."""
    return {"service": "mock_portal", "status": "ok"}


@app.post("/applications", response_model=None)
async def submit_application(request: ApplicationRequest) -> dict[str, str] | JSONResponse:
    global _next_reference
    if request.scheme_id not in REQUIRED_FIELDS:
        raise HTTPException(status_code=404, detail="unknown scheme")
    if _fail_mode == "timeout":
        await asyncio.sleep(60)
    if _fail_mode == "reject_permanent":
        return JSONResponse(
            status_code=409,
            content={"code": "duplicate_application", "message": "MOCK application already exists"},
        )

    missing = [
        {
            "field": field,
            "code": "missing_field",
            "message": f"Missing required field: {field}",
        }
        for field in REQUIRED_FIELDS[request.scheme_id]
        if request.payload_fields.get(field) in (None, "")
    ]
    if missing:
        return JSONResponse(status_code=422, content={"errors": missing})

    portal_ref = f"MOCK-PORTAL-{_next_reference:04d}"
    _next_reference += 1
    _applications[portal_ref] = {
        "scheme_id": request.scheme_id,
        "payload_fields": dict(request.payload_fields),
        "status": "accepted",
    }
    return {"portal_ref": portal_ref}


@app.get("/applications/{portal_ref}")
async def get_application(portal_ref: str) -> dict[str, str]:
    application = _applications.get(portal_ref)
    if application is None:
        raise HTTPException(status_code=404, detail="application not found")
    return {"portal_ref": portal_ref, "status": str(application["status"])}


@app.post("/dev/config")
async def configure_dev(request: DevConfigRequest) -> dict[str, str]:
    global _fail_mode
    if os.getenv("ENV", "dev") == "prod":
        raise HTTPException(status_code=404, detail="development configuration is disabled")
    if request.fail_mode not in _FAIL_MODES:
        raise HTTPException(
            status_code=422,
            detail="fail_mode must be none, timeout, or reject_permanent",
        )
    _fail_mode = request.fail_mode
    return {"fail_mode": _fail_mode}
