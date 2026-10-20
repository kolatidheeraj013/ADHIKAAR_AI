"""Database engine/session helpers for local and deployed environments."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        kwargs = {"connect_args": connect_args, "pool_pre_ping": True}
        # Keep an in-memory database available to every TestClient thread.
        if ":memory:" in database_url or database_url in {"sqlite://", "sqlite:"}:
            kwargs["poolclass"] = StaticPool
        return create_engine(database_url, **kwargs)
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create the local schema and install SQLite's append-only audit guards."""
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        case_columns = {column["name"] for column in inspect(engine).get_columns("cases")}
        if "voice_storage_path" not in case_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE cases ADD COLUMN voice_storage_path VARCHAR(1024)"
                )
    from app.audit import install_append_only_guards

    install_append_only_guards(engine)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a committed session and roll back on failure."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
