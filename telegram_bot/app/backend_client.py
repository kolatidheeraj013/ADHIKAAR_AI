"""Small HTTP-only client for the citizen-facing backend API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class BackendHTTPError(RuntimeError):
    """A backend response that the bot can turn into a localized prompt."""

    def __init__(self, status_code: int, detail: Any = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"backend returned HTTP {status_code}")


class BackendUnavailableError(RuntimeError):
    """The bot could not connect to the backend service."""


class BackendClient:
    """Async backend client; no business or eligibility logic belongs here."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.timeout = timeout
        self._client = http_client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("X-Service-Token", self.service_token)
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response = await client.request(
                method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs
            )
        except httpx.HTTPError as exc:
            raise BackendUnavailableError from exc
        finally:
            if self._client is None:
                await client.aclose()
        if response.is_error:
            try:
                detail: Any = response.json()
            except ValueError:
                detail = response.text
            raise BackendHTTPError(response.status_code, detail)
        if not response.content:
            return None
        return response.json()

    async def active_case(self, chat_id: int | str) -> dict[str, Any] | None:
        payload = await self._request(
            "GET", "/cases/active", params={"channel": "telegram", "channel_ref": str(chat_id)}
        )
        if not payload:
            return None
        if isinstance(payload, Mapping) and payload.get("case") is not None:
            return dict(payload["case"])
        return dict(payload) if isinstance(payload, Mapping) else None

    async def latest_case(self, chat_id: int | str) -> dict[str, Any] | None:
        """Return the most recent case, including a completed terminal case."""
        payload = await self._request(
            "GET", "/cases/latest", params={"channel": "telegram", "channel_ref": str(chat_id)}
        )
        if not payload:
            return None
        if isinstance(payload, Mapping) and payload.get("case") is not None:
            return dict(payload["case"])
        return dict(payload) if isinstance(payload, Mapping) else None

    async def create_case(self, language: str, chat_id: int | str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/cases",
            json={
                "language": language,
                "consent": True,
                "channel": "telegram",
                "channel_ref": str(chat_id),
            },
        )

    async def send_text(self, case_id: str, text: str) -> Any:
        return await self._request("POST", f"/cases/{case_id}/text", json={"text": text})

    async def send_voice(self, case_id: str, content: bytes, *, filename: str = "voice.ogg") -> Any:
        return await self._request(
            "POST",
            f"/cases/{case_id}/voice",
            files={"file": (filename, content, "audio/ogg")},
        )

    async def send_document(
        self,
        case_id: str,
        content: bytes,
        *,
        filename: str,
        content_type: str = "image/jpeg",
        doc_type: str | None = None,
    ) -> Any:
        params = {"doc_type": doc_type} if doc_type else {}
        return await self._request(
            "POST",
            f"/cases/{case_id}/documents",
            files={"file": (filename, content, content_type)},
            params=params,
        )

    async def classify_document(self, case_id: str, document_id: str, doc_type: str) -> Any:
        return await self._request(
            "POST",
            f"/cases/{case_id}/documents/{document_id}/classify",
            params={"doc_type": doc_type},
        )

    async def start_case(self, case_id: str) -> Any:
        return await self._request("POST", f"/cases/{case_id}/start")

    async def answer(self, case_id: str, message_id: str, option: int | str) -> Any:
        return await self._request(
            "POST",
            f"/cases/{case_id}/answers",
            json={"message_id": message_id, "option": option},
        )

    async def delete_case(self, case_id: str) -> Any:
        return await self._request("DELETE", f"/cases/{case_id}")

    async def get_case(self, case_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/cases/{case_id}")

    async def get_schemes(self) -> list[dict[str, Any]]:
        """Return the schemes currently loaded by the backend.

        The bot only presents this catalog. It deliberately does not infer
        eligibility or select a scheme from the citizen's message.
        """
        payload = await self._request("GET", "/schemes")
        if not isinstance(payload, list):
            return []
        return [dict(item) for item in payload if isinstance(item, Mapping)]
