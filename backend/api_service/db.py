"""Database engine and session management.

Plan chapter 3.2: the backend connects using a token-based identity
(Managed Identity in staging/prod, passwordless trusted connection in
local dev). The connection string is sourced from EDIM_DATABASE_URL and
falls back to a localhost default for unit tests.

The engine is created lazily and cached on app.state.db_engine so the
FastAPI composition root owns the lifecycle. A `get_session` dependency
yields a request-scoped session that auto-commits on success and
rolls back on exception.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def _resolve_database_url() -> str:
    url = os.getenv("EDIM_DATABASE_URL", "").strip()
    if url:
        return url
    # Fallback for unit tests and bare-metal dev without docker-compose.
    user = os.getenv("EDIM_DB_USER", "edim")
    password = os.getenv("EDIM_DB_PASSWORD", "edim")
    host = os.getenv("EDIM_DB_HOST", "localhost")
    port = os.getenv("EDIM_DB_PORT", "5432")
    name = os.getenv("EDIM_DB_NAME", "edim_db_local")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def build_engine(url: str | None = None) -> Engine:
    """Construct a SQLAlchemy Engine. Used by the API and the worker."""
    effective_url = url or _resolve_database_url()
    return create_engine(
        effective_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


# FastAPI dependency ---------------------------------------------------------


def get_db_session() -> Iterator[Session]:
    """Yields a request-scoped session, committing on success and rolling
    back on exception. Requires that app.state.db_session_factory is set
    by the composition root.
    """
    from fastapi import Request

    # We can't take Request as a default here because this function is
    # called as a dependency. Instead we read from contextvar.
    from .request_context import get_current_request

    request = get_current_request()
    if request is None:
        raise RuntimeError("get_db_session called outside of a request context.")

    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise RuntimeError("db_session_factory is not configured on app.state.")

    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Worker / scripts ------------------------------------------------------------


@contextmanager
def standalone_session() -> Iterator[Session]:
    """Context manager for one-off scripts (worker daemon, migrations, tests)."""
    engine = build_engine()
    factory = build_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
