"""Phase 6 : pause et reprise sûres des jobs, rendus dont les fichiers ont été nettoyés

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')"
NEW_STATUSES = "status IN ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled')"


def upgrade() -> None:
    with op.batch_alter_table("clip_renders", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("files_purged", sa.Boolean(), server_default="0", nullable=False)
        )
    with op.batch_alter_table("jobs", schema=None, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("pause_requested", sa.Boolean(), server_default="0", nullable=False)
        )
        batch_op.drop_constraint("status_valid", type_="check")
        batch_op.create_check_constraint("status_valid", NEW_STATUSES)
        batch_op.drop_index("uq_jobs_active_project_kind")
        batch_op.create_index(
            "uq_jobs_active_project_kind",
            ["project_id", "kind"],
            unique=True,
            sqlite_where=sa.text(
                "status IN ('queued', 'running', 'paused') AND kind != 'render_clip'"
            ),
        )


def downgrade() -> None:
    op.execute("UPDATE jobs SET status = 'queued' WHERE status = 'paused'")
    with op.batch_alter_table("jobs", schema=None, recreate="always") as batch_op:
        batch_op.drop_index("uq_jobs_active_project_kind")
        batch_op.create_index(
            "uq_jobs_active_project_kind",
            ["project_id", "kind"],
            unique=True,
            sqlite_where=sa.text("status IN ('queued', 'running') AND kind != 'render_clip'"),
        )
        batch_op.drop_constraint("status_valid", type_="check")
        batch_op.create_check_constraint("status_valid", OLD_STATUSES)
        batch_op.drop_column("pause_requested")
    with op.batch_alter_table("clip_renders", schema=None) as batch_op:
        batch_op.drop_column("files_purged")
