"""Retention command wrapper for the backend's local storage purge helper."""

from __future__ import annotations

import os
from pathlib import Path

from app.db.session import build_engine, build_session_factory, init_db
from app.integrations.storage import LocalStorageBackend
from app.integrations.storage import purge_expired as _purge_expired


def purge_expired(
    retention_days: int | None = None,
    storage_root: str | Path = "./private-storage",
) -> int:
    """Purge expired uploaded files using configured local development storage."""
    days = retention_days if retention_days is not None else int(os.getenv("RETENTION_DAYS", "7"))
    database_url = os.getenv("DATABASE_URL", "sqlite:///./adhikaar.db")
    engine = build_engine(database_url)
    init_db(engine)
    factory = build_session_factory(engine)
    with factory() as session:
        return _purge_expired(session, LocalStorageBackend(storage_root), days)


if __name__ == "__main__":
    print(f"Purged {purge_expired()} expired uploaded file(s).")
