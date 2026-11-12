"""Engagement : rappel en cours de vidéo et réactions de la facecam (profil)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-12 14:17:32.478004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mid_cta', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('reactions', sa.Boolean(), server_default='1', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('reactions')
        batch_op.drop_column('mid_cta')

