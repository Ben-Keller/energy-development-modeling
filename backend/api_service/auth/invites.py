from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi_users.jwt import decode_jwt, generate_jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuthInvite

logger = logging.getLogger(__name__)

INVITE_AUDIENCE = "edim:invite"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_invite(*, auth_user_id: str, email: str, secret: str, lifetime_seconds: int) -> str:
    return generate_jwt(
        {"sub": str(auth_user_id), "email": email, "aud": INVITE_AUDIENCE},
        secret,
        lifetime_seconds,
    )


def parse_invite(token: str, secret: str) -> dict | None:
    try:
        return decode_jwt(token, secret, [INVITE_AUDIENCE])
    except Exception:
        return None


async def register_invite(
    session: AsyncSession,
    *,
    auth_user_id: str,
    email: str,
    token: str,
    lifetime_seconds: int,
) -> AuthInvite:
    record = AuthInvite(
        invite_id=uuid.uuid4().hex,
        auth_user_id=str(auth_user_id),
        email=str(email),
        token_hash=_digest(token),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=lifetime_seconds),
    )
    session.add(record)
    await session.commit()
    return record


async def consume_invite(session: AsyncSession, *, auth_user_id: str, token: str) -> bool:
    stmt = select(AuthInvite).where(AuthInvite.token_hash == _digest(token))
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None or record.used_at is not None:
        return False
    if str(record.auth_user_id) != str(auth_user_id):
        return False
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return False
    record.used_at = datetime.now(timezone.utc)
    await session.commit()
    return True
