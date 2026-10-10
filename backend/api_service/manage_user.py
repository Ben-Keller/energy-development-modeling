"""Django-style user management for EDIM auth accounts.

Usage (from the directory where the ``api_service`` package lives):

    python -m api_service.manage_user <email> [options]

Given an e-mail, it creates or completes a fully usable account (active,
verified, admin by default) and returns the credentials. A fresh password is
generated and printed only when the account is new or inactive, so repeated
runs never rotate a working password; use --password to set your own or
--keep-password to leave an existing one untouched. Examples:

    python -m api_service.manage_user daniele.ciminieri@gmail.com
    python -m api_service.manage_user someone@example.org --password "..."
    python -m api_service.manage_user someone@example.org --no-admin --keep-password

It runs anywhere the backend code runs: the local dev container, the local
venv, or the deployed App Service (via the Kudu command API).
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api_service.auth.db import resolve_auth_database_url
from api_service.auth.models import AuthBase, AuthUser
from api_service.settings import get_settings


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", str(value or "").strip().lower()).strip("._")[:120]


async def _run(args: argparse.Namespace) -> int:
    from fastapi_users.password import PasswordHelper

    settings = get_settings()
    helper = PasswordHelper()
    email = args.email.strip().lower()
    admin_email = str(getattr(settings, "auth_admin_email", "") or "").strip().lower()
    is_admin = not args.no_admin
    user_id = args.user_id or ("admin" if (is_admin and email == admin_email) else _slug(email.split("@", 1)[0]) or "user")

    engine = create_async_engine(resolve_auth_database_url(settings), future=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(AuthBase.metadata.create_all)

        password = ""
        generated = False
        async with factory() as session:
            user = (await session.execute(select(AuthUser).where(func.lower(AuthUser.email) == email))).scalars().first()
            created = user is None
            if created:
                password = args.password or helper.generate()
                generated = not args.password
                user = AuthUser(
                    id=uuid.uuid4().hex,
                    user_id=user_id,
                    email=email,
                    hashed_password=helper.hash(password),
                    is_active=True,
                    is_superuser=is_admin,
                    is_verified=True,
                    display_name=args.display_name or email.split("@", 1)[0],
                    organization=args.organization or "",
                )
                session.add(user)
            else:
                was_active = bool(user.is_active)
                if not user.user_id:
                    user.user_id = user_id
                user.is_active = True
                user.is_verified = True
                if is_admin:
                    user.is_superuser = True
                if args.display_name:
                    user.display_name = args.display_name
                if args.organization:
                    user.organization = args.organization
                if args.password:
                    password = args.password
                    user.hashed_password = helper.hash(password)
                elif not args.keep_password and (args.rotate_password or not was_active):
                    password = helper.generate()
                    generated = True
                    user.hashed_password = helper.hash(password)
            await session.commit()
            await session.refresh(user)
            stored_hash = user.hashed_password
    finally:
        await engine.dispose()

    login_ok = False
    if password:
        login_ok = bool(helper.verify_and_update(password, stored_hash)[0])

    print(f"user_id      : {user.user_id}")
    print(f"email        : {user.email}")
    print(f"display_name : {user.display_name}")
    print(f"is_admin     : {bool(user.is_superuser)}")
    print(f"is_active    : {bool(user.is_active)}")
    print(f"created      : {created}")
    print(f"login check  : {'OK' if login_ok else ('n/a (password untouched)' if not password else 'FAILED')}")
    if password and generated:
        print(f"password     : {password}")
        print(f"EDIM_MANAGE_USER_PASSWORD={password}")
        print("change it at /auth/change-password after the first sign-in")
    elif password:
        print("password     : (as provided)")
    else:
        print("password     : (unchanged)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m api_service.manage_user", description="Create or complete an EDIM account given an e-mail (like Django's createsuperuser).")
    parser.add_argument("email", help="account e-mail")
    parser.add_argument("--password", default="", help="set this password (otherwise one is generated and printed)")
    parser.add_argument("--keep-password", action="store_true", help="do not touch the password of an existing account")
    parser.add_argument("--rotate-password", action="store_true", help="force a fresh generated password even for an active account")
    parser.add_argument("--no-admin", action="store_true", help="create a regular (non-admin) account")
    parser.add_argument("--user-id", default="", help="ownership user_id (default: derived from the e-mail)")
    parser.add_argument("--display-name", default="", help="display name")
    parser.add_argument("--organization", default="", help="organization")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
