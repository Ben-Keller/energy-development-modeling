from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Tuple

DEFAULT_USER_ID = "undp_analyst"
AUTH_MODE_TEST_HEADER = "test_user_header"


@dataclass(frozen=True)
class UserContext:
    """Authenticated user context passed from API dependencies to services.

    The local implementation is backed by seeded test users, but production
    auth should preserve this shape so downstream project/run ownership logic
    does not depend on a specific identity provider.
    """

    user_id: str
    display_name: str = ""
    email: str = ""
    organization: str = ""
    roles: Tuple[str, ...] = ()
    is_admin: bool = False
    auth_mode: str = AUTH_MODE_TEST_HEADER

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "email": self.email,
            "organization": self.organization,
            "roles": list(self.roles),
            "is_admin": bool(self.is_admin),
            "auth_mode": self.auth_mode,
        }

TEST_USERS: List[Dict[str, Any]] = [
    {
        "user_id": "admin",
        "display_name": "Platform Admin",
        "email": "admin@example.org",
        "organization": "UNDP",
        "roles": ["platform_admin", "model_runner"],
        "is_admin": True,
    },
    {
        "user_id": "undp_analyst",
        "display_name": "UNDP Analyst",
        "email": "analyst@example.org",
        "organization": "UNDP",
        "roles": ["model_runner"],
        "is_admin": False,
    },
    {
        "user_id": "country_officer",
        "display_name": "Country Officer",
        "email": "country.officer@example.org",
        "organization": "Partner government",
        "roles": ["project_member", "model_runner"],
        "is_admin": False,
    },
]


def normalize_user_id(value: str | None, default: str = DEFAULT_USER_ID) -> str:
    text = str(value or default).strip()
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:120]
    return normalized or default


def list_test_users() -> List[Dict[str, Any]]:
    return [dict(row) for row in TEST_USERS]


def _test_user_by_id() -> Dict[str, Dict[str, Any]]:
    return {str(row["user_id"]): row for row in TEST_USERS}


def is_known_test_user(value: str | None) -> bool:
    return normalize_user_id(value) in _test_user_by_id()


def resolve_test_user(value: str | None) -> Dict[str, Any]:
    user_id = normalize_user_id(value)
    users = _test_user_by_id()
    row = users.get(user_id) or users.get(DEFAULT_USER_ID)
    return dict(row or TEST_USERS[0])


def resolve_user_context(value: str | None, *, auth_mode: str = AUTH_MODE_TEST_HEADER) -> UserContext:
    row = resolve_test_user(value)
    roles = tuple(str(role) for role in (row.get("roles") or []) if str(role))
    is_admin = bool(row.get("is_admin") or "platform_admin" in roles)
    return UserContext(
        user_id=normalize_user_id(str(row.get("user_id") or DEFAULT_USER_ID)),
        display_name=str(row.get("display_name") or ""),
        email=str(row.get("email") or ""),
        organization=str(row.get("organization") or ""),
        roles=roles,
        is_admin=is_admin,
        auth_mode=auth_mode,
    )


def is_admin_user(user_id: str | None) -> bool:
    user = _test_user_by_id().get(normalize_user_id(user_id, ""))
    if not user:
        return False
    return bool(user.get("is_admin") or "platform_admin" in user.get("roles", []))
