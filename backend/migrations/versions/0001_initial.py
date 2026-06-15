"""initial EDIM schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-14 14:00:00.000000

Implements plan chapter 3.3 (relational data model):

  - users                          (plan 3.3.1)
  - projects                       (plan 3.3.1)
  - project_runs                   (plan 3.3.1, 3.3.2, 6.3)
  - execution_attempts             (plan 6.5)
  - dataset_version_metadata       (plan 3.3.1, 5.2.1)
  - dataset_version_pointers       (plan 3.3.1, 5.2.2)
  - project_runs_dataset_versions  (plan 3.3.2, 5.3 reference locking)
  - reports                        (plan 3.3.1, 9.1)
  - exports                        (plan 3.3.1, 9.2)
  - execution_events               (plan 8.3, 8.5)

All tables carry owner_user_id for mandatory ownership filtering
(plan 2.3.1, 3.5). The project_runs_dataset_versions table enforces
reference locking via FK ON DELETE RESTRICT against
dataset_version_metadata (plan 3.3.2, 5.3).
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=255), primary_key=True),
        sa.Column("display_name", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("organization", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("auth_mode", sa.String(length=32), nullable=False, server_default="test_header"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=255), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("geography_code", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("geography_label", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("use_case_label", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"])
    op.create_index("ix_projects_owner_updated", "projects", ["owner_user_id", "updated_at"])

    op.create_table(
        "project_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("active_execution_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("execution_queue_message", sa.JSON(), nullable=True),
        sa.Column("run_profile", sa.String(length=32), nullable=False, server_default="dev"),
        sa.Column("energy_scenario_key", sa.String(length=128), nullable=False),
        sa.Column("mrio_scenario_id", sa.String(length=64), nullable=False),
        sa.Column("target_year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_project_runs_project_id", "project_runs", ["project_id"])
    op.create_index("ix_project_runs_owner_user_id", "project_runs", ["owner_user_id"])
    op.create_index("ix_project_runs_owner_updated", "project_runs", ["owner_user_id", "updated_at"])
    op.create_index("ix_project_runs_status", "project_runs", ["status"])

    op.create_table(
        "execution_attempts",
        sa.Column("attempt_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("project_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("execution_id", "attempt_count", name="uq_execution_attempt"),
    )
    op.create_index("ix_execution_attempts_run_id", "execution_attempts", ["run_id"])
    op.create_index("ix_execution_attempts_execution_id", "execution_attempts", ["execution_id"])

    op.create_table(
        "dataset_version_metadata",
        sa.Column("dataset_version_id", sa.String(length=64), primary_key=True),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("validation_metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("dataset_id", "file_hash", name="uq_dataset_version_hash"),
    )
    op.create_index("ix_dataset_version_metadata_dataset_id", "dataset_version_metadata", ["dataset_id"])
    op.create_index("ix_dataset_version_metadata_owner_user_id", "dataset_version_metadata", ["owner_user_id"])

    op.create_table(
        "dataset_version_pointers",
        sa.Column("dataset_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "active_version_id",
            sa.String(length=64),
            sa.ForeignKey("dataset_version_metadata.dataset_version_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dataset_version_pointers_owner_user_id", "dataset_version_pointers", ["owner_user_id"])

    op.create_table(
        "project_runs_dataset_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("project_runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.String(length=64), nullable=False),
        sa.Column(
            "dataset_version_id",
            sa.String(length=64),
            sa.ForeignKey("dataset_version_metadata.dataset_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "dataset_id", name="uq_run_dataset"),
    )
    op.create_index(
        "ix_project_runs_dataset_versions_run_id", "project_runs_dataset_versions", ["run_id"]
    )

    op.create_table(
        "reports",
        sa.Column("report_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("selected_run_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("storage_ref", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_reports_project_id", "reports", ["project_id"])
    op.create_index("ix_reports_owner_user_id", "reports", ["owner_user_id"])

    op.create_table(
        "exports",
        sa.Column("export_id", sa.String(length=64), primary_key=True),
        sa.Column("project_id", sa.String(length=64), sa.ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("storage_ref", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_exports_project_id", "exports", ["project_id"])
    op.create_index("ix_exports_owner_user_id", "exports", ["owner_user_id"])

    op.create_table(
        "execution_events",
        sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("stage", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_execution_events_execution_id", "execution_events", ["execution_id"])
    op.create_index("ix_execution_events_run_id", "execution_events", ["run_id"])
    op.create_index("ix_execution_events_exec_ts", "execution_events", ["execution_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_execution_events_exec_ts", table_name="execution_events")
    op.drop_index("ix_execution_events_run_id", table_name="execution_events")
    op.drop_index("ix_execution_events_execution_id", table_name="execution_events")
    op.drop_table("execution_events")

    op.drop_index("ix_exports_owner_user_id", table_name="exports")
    op.drop_index("ix_exports_project_id", table_name="exports")
    op.drop_table("exports")

    op.drop_index("ix_reports_owner_user_id", table_name="reports")
    op.drop_index("ix_reports_project_id", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_project_runs_dataset_versions_run_id", table_name="project_runs_dataset_versions")
    op.drop_table("project_runs_dataset_versions")

    op.drop_index("ix_dataset_version_pointers_owner_user_id", table_name="dataset_version_pointers")
    op.drop_table("dataset_version_pointers")

    op.drop_index("ix_dataset_version_metadata_owner_user_id", table_name="dataset_version_metadata")
    op.drop_index("ix_dataset_version_metadata_dataset_id", table_name="dataset_version_metadata")
    op.drop_table("dataset_version_metadata")

    op.drop_index("ix_execution_attempts_execution_id", table_name="execution_attempts")
    op.drop_index("ix_execution_attempts_run_id", table_name="execution_attempts")
    op.drop_table("execution_attempts")

    op.drop_index("ix_project_runs_status", table_name="project_runs")
    op.drop_index("ix_project_runs_owner_updated", table_name="project_runs")
    op.drop_index("ix_project_runs_owner_user_id", table_name="project_runs")
    op.drop_index("ix_project_runs_project_id", table_name="project_runs")
    op.drop_table("project_runs")

    op.drop_index("ix_projects_owner_updated", table_name="projects")
    op.drop_index("ix_projects_owner_user_id", table_name="projects")
    op.drop_table("projects")

    op.drop_table("users")
