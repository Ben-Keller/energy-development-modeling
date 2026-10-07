from __future__ import annotations

import logging

from fastapi import Request
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, CookieTransport, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase

from ..services.users import UserContext
from .db import _bind, ensure_ready
from .manager import EdimUserManager, get_user_manager
from .models import AuthUser

logger = logging.getLogger(__name__)

_settings = None
_backend: AuthenticationBackend | None = None
_instance: FastAPIUsers | None = None

AUTH_MODE_LOCAL_PASSWORD = "local_password"


def configure_auth(settings) -> None:
    global _settings, _backend, _instance
    _settings = settings
    _backend = None
    _instance = None


def auth_settings():
    return _settings


def auth_backend() -> AuthenticationBackend:
    global _backend
    if _backend is None:
        s = _settings
        transport = CookieTransport(
            cookie_name=s.auth_cookie_name,
            cookie_max_age=s.auth_session_ttl_seconds,
            cookie_path="/",
            cookie_secure=s.auth_cookie_secure,
            cookie_httponly=True,
            cookie_samesite="lax",
        )
        _backend = AuthenticationBackend(
            name="cookie",
            transport=transport,
            get_strategy=lambda: JWTStrategy(
                secret=s.auth_session_secret,
                lifetime_seconds=s.auth_session_ttl_seconds,
            ),
        )
    return _backend


def fastapi_users() -> FastAPIUsers:
    global _instance
    if _instance is None:
        _instance = FastAPIUsers[AuthUser, str](get_user_manager, [auth_backend()])
    return _instance


def build_user_manager(request: Request) -> EdimUserManager:
    s = request.app.state.settings
    _engine, factory = _bind(s)
    session = factory()
    manager = EdimUserManager(SQLAlchemyUserDatabase(session, AuthUser))
    manager.reset_password_token_secret = s.auth_session_secret
    manager.verification_token_secret = s.auth_session_secret
    manager.reset_password_token_lifetime_seconds = s.auth_reset_ttl_seconds
    manager.password_min_length = s.auth_password_min_length
    return manager


async def resolve_session_context(request: Request) -> UserContext | None:
    await ensure_ready(request)
    backend = auth_backend()
    strategy = backend.get_strategy()
    token = await backend.transport.scheme(request)
    if not token:
        return None
    manager = build_user_manager(request)
    try:
        user = await strategy.read_token(token, manager)
        if user is None or not user.is_active:
            return None
        return _to_context(user)
    finally:
        await manager.user_db.session.close()


def _to_context(user: AuthUser) -> UserContext:
    return UserContext(
        user_id=str(user.user_id or user.id),
        display_name=str(user.display_name or ""),
        email=str(user.email or ""),
        organization=str(user.organization or ""),
        roles=(),
        is_admin=bool(user.is_superuser),
        auth_mode=AUTH_MODE_LOCAL_PASSWORD,
    )
