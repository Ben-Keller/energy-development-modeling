from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import Depends, Request
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import AuthBase, AuthUser

logger = logging.getLogger(__name__)

_engines: dict[int, tuple[AsyncEngine, async_sessionmaker[AsyncSession]]] = {}
_init_locks: dict[int, asyncio.Lock] = {}


def resolve_auth_database_url(settings) -> str:
    explicit = os.getenv("EDIM_AUTH_DATABASE_URL", "").strip()
    if explicit:
        return _as_async_url(explicit)
    app_url = os.getenv("EDIM_DATABASE_URL", "").strip()
    if app_url:
        return _as_async_url(app_url)
    configured = str(getattr(settings, "platform_sqlite_path", "") or "").strip()
    base = Path(configured).expanduser() if configured else Path(settings.runs_dir).parent / "platform" / "platform.sqlite3"
    return f"sqlite+aiosqlite:///{base.parent / 'auth.sqlite3'}"


def _as_async_url(url: str) -> str:
    if url.startswith("sqlite://") and not url.startswith("sqlite+"):
        return "sqlite+aiosqlite://" + url[len("sqlite://") :]
    return url


def _bind(settings):
    loop_id = id(asyncio.get_running_loop())
    entry = _engines.get(loop_id)
    if entry is None:
        engine = create_async_engine(resolve_auth_database_url(settings), future=True)
        entry = (engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
        _engines[loop_id] = entry
    return entry


async def ensure_ready(request: Request) -> None:
    state = request.app.state
    if getattr(state, "auth_ready", False):
        return
    loop_id = id(asyncio.get_running_loop())
    lock = _init_locks.setdefault(loop_id, asyncio.Lock())
    async with lock:
        if getattr(state, "auth_ready", False):
            return
        engine, factory = _bind(state.settings)
        async with engine.begin() as conn:
            await conn.run_sync(AuthBase.metadata.create_all)
        async with factory() as session:
            from .bootstrap import seed_if_empty

            await seed_if_empty(session, state.settings)
        state.auth_ready = True


async def get_auth_session(request: Request):
    await ensure_ready(request)
    _engine, factory = _bind(request.app.state.settings)
    async with factory() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_auth_session)):
    yield SQLAlchemyUserDatabase(session, AuthUser)
