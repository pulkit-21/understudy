"""Schedules table — recurring, unattended workflow triggers."""
import sqlalchemy as sa

from alembic import op

revision = "0003_schedules"
down_revision = "0002_workflow_version_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schedules_org_id", "schedules", ["org_id"])
    op.create_index("ix_schedules_workflow_id", "schedules", ["workflow_id"])
    op.create_index("ix_schedules_enabled", "schedules", ["enabled"])
    op.create_index("ix_schedules_next_run_at", "schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_table("schedules")
