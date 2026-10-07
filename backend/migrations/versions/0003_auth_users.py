"""Add fastapi-users auth tables

Revision ID: 0003_auth_users
Revises: 0002_platform_json_store
Create Date: 2026-10-07 09:00:00.000000

Adds the credential and invitation tables used by the fastapi-users
integration. Application data continues to reference owner_user_id strings
in platform_records; these tables only own authentication state.
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_auth_users"
down_revision = "0002_platform_json_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("organization", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_users_email", "auth_users", ["email"], unique=True)
    op.create_index("ix_auth_users_user_id", "auth_users", ["user_id"], unique=True)

    op.create_table(
        "auth_invites",
        sa.Column("invite_id", sa.String(length=64), primary_key=True),
        sa.Column("auth_user_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_auth_invites_auth_user_id", "auth_invites", ["auth_user_id"])
    op.create_index("ix_auth_invites_token_hash", "auth_invites", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_auth_invites_token_hash", table_name="auth_invites")
    op.drop_index("ix_auth_invites_auth_user_id", table_name="auth_invites")
    op.drop_table("auth_invites")
    op.drop_index("ix_auth_users_user_id", table_name="auth_users")
    op.drop_index("ix_auth_users_email", table_name="auth_users")
    op.drop_table("auth_users")
