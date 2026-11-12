"""Barre de progression (réglage de profil)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-12 13:39:19.238275
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('progress_bar', sa.Boolean(), server_default='1', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('progress_bar')

