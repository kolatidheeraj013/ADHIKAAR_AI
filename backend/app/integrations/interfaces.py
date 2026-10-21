"""Protocols for external boundaries used by backend nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class StorageBackend(Protocol):
    """Private file storage contract shared by local and production backends."""

    def store(self, case_id: str, filename: str, content: bytes) -> str:
        """Persist bytes and return an opaque storage path."""

    def retrieve(self, storage_path: str) -> bytes:
        """Read bytes from an opaque storage path."""

    def delete(self, storage_path: str) -> None:
        """Delete a stored object if it exists."""


class PathLikeStorage(Protocol):
    """Optional protocol for implementations exposing their root directory."""

    root: Path


class SpeechClient(Protocol):
    def transcribe(self, voice_path: str, language: str) -> str: ...


class OCRClient(Protocol):
    def ocr(self, path: str) -> dict[str, Any]: ...


class DocClassifier(Protocol):
    def classify(self, path: str) -> dict[str, Any]: ...


class LLMClient(Protocol):
    def extract_facts(
        self, text: str, source_type: str, source_doc_id: str | None, target_keys: list[str]
    ) -> dict[str, Any]: ...

    def extract_field(self, text: str, field: str, source_doc_id: str | None) -> Any: ...

    def explain(self, outcome: str, trace: list[dict[str, Any]], language: str) -> str: ...


class PortalClient(Protocol):
    def submit(self, scheme_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def verify(self, portal_ref: str) -> dict[str, Any]: ...


class Retriever(Protocol):
    def retrieve(self, query: str, k: int = 4) -> list[dict[str, Any]]: ...


class Notifier(Protocol):
    def notify(
        self,
        case_id: str,
        language: str,
        kind: str,
        text: str,
        options: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> bool | None: ...
