from __future__ import annotations

from typing import Optional

from fastapi_users import schemas


class UserRead(schemas.BaseUser[str]):
    user_id: str = ""
    display_name: str = ""
    organization: str = ""


class UserCreate(schemas.BaseUserCreate):
    user_id: str = ""
    display_name: str = ""
    organization: str = ""


class UserUpdate(schemas.BaseUserUpdate):
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    organization: Optional[str] = None
