from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.users import TEST_USERS
from .invites import mint_invite, register_invite
from .models import AuthUser

logger = logging.getLogger(__name__)


async def seed_if_empty(session: AsyncSession, settings) -> None:
    count = (await session.execute(select(func.count(AuthUser.id)))).scalar_one()
    if count:
        return
    from fastapi_users.password import PasswordHelper

    helper = PasswordHelper()
    seeded_password = os.getenv("EDIM_AUTH_SEED_PASSWORD", "").strip()
    for row in TEST_USERS:
        user_id = str(row["user_id"])
        password = seeded_password or helper.generate()
        user = AuthUser(
            id=uuid.uuid4().hex,
            user_id=user_id,
            email=str(row.get("email") or f"{user_id}@example.org"),
            hashed_password=helper.hash(password),
            is_active=bool(seeded_password),
            is_superuser=bool(row.get("is_admin")),
            is_verified=True,
            display_name=str(row.get("display_name") or user_id),
            organization=str(row.get("organization") or ""),
        )
        session.add(user)
        await session.flush()
        if seeded_password:
            logger.warning("auth.seed user_id=%s active with the shared seed password", user_id)
            continue
        token = mint_invite(
            auth_user_id=str(user.id),
            email=user.email,
            secret=settings.auth_session_secret,
            lifetime_seconds=settings.auth_invite_ttl_seconds,
        )
        await register_invite(
            session,
            auth_user_id=str(user.id),
            email=user.email,
            token=token,
            lifetime_seconds=settings.auth_invite_ttl_seconds,
        )
        logger.warning("auth.seed INVITE for %s: /auth/invite?token=%s", user_id, token)
    await session.commit()
    if not seeded_password:
        logger.warning("auth.seed created %d inactive users; open the invite links above to set passwords", len(TEST_USERS))
