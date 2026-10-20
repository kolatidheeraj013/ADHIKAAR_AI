"""HTTP client for the deterministic ADHIKAAR mock portal."""

from __future__ import annotations

import os
from typing import Any

import httpx


class PortalClient:
    """Small synchronous client implementing the graph's portal protocol."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | httpx.Timeout | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("MOCK_PORTAL_URL", "http://localhost:8100")).rstrip(
            "/"
        )
        configured_timeout = float(os.getenv("MOCK_PORTAL_TIMEOUT_SECONDS", "5"))
        self.timeout = timeout if timeout is not None else configured_timeout
        self._client = client or httpx.Client(timeout=self.timeout)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PortalClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def submit(self, scheme_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                f"{self.base_url}/applications",
                json={"scheme_id": scheme_id, "payload_fields": payload},
            )
        except httpx.TimeoutException:
            return self._error("timeout", "timeout", "MOCK portal request timed out")
        except httpx.RequestError:
            return self._error(
                "transient", "network_error", "MOCK portal is temporarily unavailable"
            )
        return self._decode(response, success_keys=("portal_ref",))

    def verify(self, portal_ref: str) -> dict[str, Any]:
        try:
            response = self._client.get(f"{self.base_url}/applications/{portal_ref}")
        except httpx.TimeoutException:
            return self._error("timeout", "timeout", "MOCK portal request timed out")
        except httpx.RequestError:
            return self._error(
                "transient", "network_error", "MOCK portal is temporarily unavailable"
            )
        result = self._decode(response, success_keys=("status",))
        if result.get("ok"):
            result["portal_ref"] = portal_ref
        return result

    @staticmethod
    def _error(kind: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
        return {"ok": False, "error": {"kind": kind, "code": code, "message": message, **extra}}

    def _decode(self, response: httpx.Response, *, success_keys: tuple[str, ...]) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.is_success:
            if all(key in body for key in success_keys):
                return {"ok": True, **body}
            return self._error(
                "transient", "invalid_response", "MOCK portal returned an invalid response"
            )

        if response.status_code >= 500:
            return self._error(
                "transient",
                f"http_{response.status_code}",
                "MOCK portal returned a temporary server error",
                status=response.status_code,
            )

        errors = body.get("errors") if isinstance(body, dict) else None
        first_error = errors[0] if isinstance(errors, list) and errors else {}
        code = str(first_error.get("code", body.get("code", "portal_rejected")))
        kind = "validation" if code == "missing_field" else "permanent"
        error: dict[str, Any] = {
            "kind": kind,
            "code": code,
            "message": str(
                first_error.get("message")
                or body.get("message")
                or "MOCK portal rejected the application"
            ),
        }
        if first_error.get("field"):
            error["field"] = str(first_error["field"])
        return {"ok": False, "error": error}


HttpPortalClient = PortalClient
