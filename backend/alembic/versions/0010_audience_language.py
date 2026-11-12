"""Public visé par rendu (version française ou anglaise)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12 00:10:01.164473
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('audience_language', sa.String(length=5), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.drop_column('audience_language')

