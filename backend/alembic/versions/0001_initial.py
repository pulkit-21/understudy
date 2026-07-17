"""initial schema: orgs, users, traces, workflows, workflow_versions, runs

Consolidated during pre-data development (no production rows to migrate) so the
multi-tenant schema lands in one revision rather than a churn of ALTERs.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_org_id", "users", ["org_id"])

    op.create_table(
        "traces",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_traces_started_at", "traces", ["started_at"])
    op.create_index("ix_traces_org_id", "traces", ["org_id"])

    op.create_table(
        "workflows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False,
                  server_default="published"),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("param_keys", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_workflows_org_id", "workflows", ["org_id"])
    op.create_index("ix_workflows_status", "workflows", ["status"])

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_workflow_versions_workflow_id", "workflow_versions",
                    ["workflow_id"])
    op.create_index("ix_workflow_versions_org_id", "workflow_versions",
                    ["org_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_runs_org_id", "runs", ["org_id"])
    op.create_index("ix_runs_workflow_id", "runs", ["workflow_id"])
    op.create_index("ix_runs_batch_id", "runs", ["batch_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("workflow_versions")
    op.drop_table("workflows")
    op.drop_table("traces")
    op.drop_table("users")
    op.drop_table("orgs")
