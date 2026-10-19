"""Private local storage backend and retention purge helper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document
from app.integrations.interfaces import StorageBackend


class LocalStorageBackend:
    """Store opaque files below a private root, never using user filenames."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, case_id: str, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix and not suffix.isalnum() and suffix not in {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".ogg",
        }:
            suffix = ".bin"
        if not suffix:
            suffix = ".bin"
        case_dir = self._safe_case_dir(case_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        relative_path = PurePosixPath(case_id, f"{uuid4().hex}{suffix}")
        destination = self._resolve(relative_path.as_posix())
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
        return relative_path.as_posix()

    def retrieve(self, storage_path: str) -> bytes:
        return self._resolve(storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        path = self._resolve(storage_path)
        if path.exists():
            path.unlink()

    def _safe_case_dir(self, case_id: str) -> Path:
        if not case_id or Path(case_id).name != case_id or case_id in {".", ".."}:
            raise ValueError("case_id must be one safe path component")
        return self._resolve(case_id)

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("storage path escapes the private storage root")
        return candidate


def purge_expired(
    session: Session,
    storage: StorageBackend,
    retention_days: int,
    *,
    now: datetime | None = None,
) -> int:
    """Remove expired uploaded files while retaining the document audit metadata."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)
    expired = session.scalars(
        select(Document).where(
            Document.storage_path.is_not(None),
            Document.created_at < cutoff,
        )
    ).all()
    for document in expired:
        if document.storage_path:
            storage.delete(document.storage_path)
            document.storage_path = None
    session.commit()
    return len(expired)
