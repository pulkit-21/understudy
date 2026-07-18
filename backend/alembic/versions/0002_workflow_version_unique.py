"""Unique (workflow_id, version) on workflow_versions.

version_payload() looks a snapshot up with scalar_one_or_none(), which raises if
two rows ever share (workflow_id, version). Every write path bumps the version
first, so it's currently held only by discipline — this makes it the schema's
guarantee. Uses batch mode so it also applies on SQLite (no ALTER ADD CONSTRAINT).
"""
from alembic import op

revision = "0002_workflow_version_unique"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_versions") as batch:
        batch.create_unique_constraint(
            "uq_workflow_version", ["workflow_id", "version"])


def downgrade() -> None:
    with op.batch_alter_table("workflow_versions") as batch:
        batch.drop_constraint("uq_workflow_version", type_="unique")
