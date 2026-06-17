"""Add platform_records JSON store

Revision ID: 0002_platform_json_store
Revises: 0001_initial
Create Date: 2026-06-17 12:00:00.000000

Adds the platform_records table used by PostgresPlatformRepository.
This is a key/value JSON blob store for projects, runs, reports, and
exports. It mirrors the SQLitePlatformRepository schema so the same
business logic works over both backends without schema mapping.
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_platform_json_store"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_records",
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("record_id", sa.String(length=128), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("execution_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("kind", "record_id"),
    )
    op.create_index("ix_platform_records_owner_kind", "platform_records", ["owner_user_id", "kind"])
    op.create_index("ix_platform_records_project_kind", "platform_records", ["project_id", "kind"])
    op.create_index("ix_platform_records_execution", "platform_records", ["execution_id"])
    op.create_index("ix_platform_records_status_kind", "platform_records", ["status", "kind"])


def downgrade() -> None:
    op.drop_index("ix_platform_records_status_kind", table_name="platform_records")
    op.drop_index("ix_platform_records_execution", table_name="platform_records")
    op.drop_index("ix_platform_records_project_kind", table_name="platform_records")
    op.drop_index("ix_platform_records_owner_kind", table_name="platform_records")
    op.drop_table("platform_records")
