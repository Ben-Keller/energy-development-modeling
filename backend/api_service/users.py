"""User identity and authentication boundary.

Implements plan chapter 2 (Identity, Authentication & Multi-Tenancy) as a
seam that can be swapped between the local test-header shim and the
production OIDC validator without changing downstream code.

Resolution chain (plan 2.2):
  1. EDIM_AUTH_MODE=oidc        -> validate JWT against Entra ID discovery
                                   endpoint, extract claims into UserContext.
  2. EDIM_AUTH_MODE=test_header -> read X-EDIM-User-Id header; build a
                                   UserContext with admin=False (plan 1.4).
  3. EDIM_AUTH_MODE=disabled    -> reject all authenticated requests; only
                                   /api/system/manifest and /health are public.

The UserContext is the stable object consumed by repositories (plan 2.2.2).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from fastapi import Depends, Header, HTTPException, Request, status

logger = logging.getLogger(__name__)


class AuthMode(str, Enum):
    OIDC = "oidc"
    TEST_HEADER = "test_header"
    DISABLED = "disabled"


def resolve_auth_mode() -> AuthMode:
    raw = os.getenv("EDIM_AUTH_MODE", AuthMode.TEST_HEADER.value).strip().lower()
    try:
        return AuthMode(raw)
    except ValueError:
        logger.warning("Unknown EDIM_AUTH_MODE=%s; falling back to test_header", raw)
        return AuthMode.TEST_HEADER


@dataclass(frozen=True)
class UserContext:
    """The stable identity object consumed by repositories and services.

    Field names are part of the public contract (plan 2.2.2). Do not rename
    without coordinating with the frontend and any persisted references.
    """

    user_id: str
    display_name: str
    email: str
    organization: str
    roles: tuple[str, ...]
    is_admin: bool
    auth_mode: AuthMode

    def has_role(self, role: str) -> bool:
        return role in self.roles


# ---------------------------------------------------------------------------
# Provider functions. The composition root in main.py picks one based on
# EDIM_AUTH_MODE at startup. Tests can override by directly setting
# app.state.auth_provider.
# ---------------------------------------------------------------------------

AuthProvider = Callable[[Request], Awaitable[UserContext]]


def _parse_test_header(x_user_id: Optional[str], x_user_name: Optional[str], x_user_email: Optional[str], x_user_org: Optional[str], x_user_roles: Optional[str]) -> UserContext:
    user_id = (x_user_id or os.getenv("EDIM_TEST_USER_ID") or "dev-user-1").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-EDIM-User-Id.")
    display_name = (x_user_name or user_id).strip()
    email = (x_user_email or f"{user_id}@dev.local").strip()
    organization = (x_user_org or "local-dev").strip()
    roles_raw = (x_user_roles or "").strip()
    roles: tuple[str, ...] = tuple(r.strip() for r in roles_raw.split(",") if r.strip())
    is_admin = "EDIM.Admin" in roles or "admin" in roles
    return UserContext(
        user_id=user_id,
        display_name=display_name,
        email=email,
        organization=organization,
        roles=roles,
        is_admin=is_admin,
        auth_mode=AuthMode.TEST_HEADER,
    )


async def test_header_auth_provider(request: Request) -> UserContext:
    """Plan 1.4: develop-branch test-header shim. Used for local Docker only."""
    return _parse_test_header(
        request.headers.get("X-EDIM-User-Id"),
        request.headers.get("X-EDIM-User-Name"),
        request.headers.get("X-EDIM-User-Email"),
        request.headers.get("X-EDIM-User-Org"),
        request.headers.get("X-EDIM-User-Roles"),
    )


async def oidc_auth_provider(request: Request) -> UserContext:
    """Plan 2.2: validate Bearer JWT against Entra ID, extract claims.

    Implementation: standard OIDC discovery + JWKS validation. The actual
    JWT decode is delegated to a helper so this function stays focused on
    claim mapping.
    """
    from .oidc import validate_bearer_token   # local helper, import-guarded

    auth = request.headers.get("Authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")
    token = auth.split(" ", 1)[1].strip()
    claims = await validate_bearer_token(token)
    return _claims_to_user_context(claims, AuthMode.OIDC)


def _claims_to_user_context(claims: dict[str, Any], mode: AuthMode) -> UserContext:
    user_id = str(claims.get("sub") or claims.get("oid") or "").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject.")
    display_name = str(claims.get("name") or user_id).strip()
    email = str(claims.get("preferred_username") or claims.get("email") or "").strip()
    organization = str(claims.get("organization") or claims.get("tid") or "").strip()
    roles_raw = claims.get("roles") or claims.get("groups") or []
    if isinstance(roles_raw, str):
        roles: tuple[str, ...] = tuple(r.strip() for r in roles_raw.split(",") if r.strip())
    else:
        roles = tuple(str(r).strip() for r in roles_raw if str(r).strip())
    is_admin = "EDIM.Admin" in roles
    return UserContext(
        user_id=user_id,
        display_name=display_name,
        email=email,
        organization=organization,
        roles=roles,
        is_admin=is_admin,
        auth_mode=mode,
    )


async def disabled_auth_provider(request: Request) -> UserContext:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is disabled for this deployment.",
    )


def build_auth_provider(mode: AuthMode) -> AuthProvider:
    if mode == AuthMode.OIDC:
        return oidc_auth_provider
    if mode == AuthMode.DISABLED:
        return disabled_auth_provider
    return test_header_auth_provider


# ---------------------------------------------------------------------------
# FastAPI dependency. The provider is looked up from app.state at request
# time so deployments can change the auth mode without restarting workers.
# ---------------------------------------------------------------------------


async def get_current_user_context(request: Request) -> UserContext:
    provider: Optional[AuthProvider] = getattr(request.app.state, "auth_provider", None)
    if provider is None:
        provider = build_auth_provider(resolve_auth_mode())
    return await provider(request)


def require_admin(user: UserContext = Depends(get_current_user_context)) -> UserContext:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
    return user
