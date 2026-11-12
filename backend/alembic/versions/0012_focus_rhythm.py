"""Disposition gros plan qui suit le visage (par défaut) et recadrages rythmés

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-12 12:54:46.569338
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('jump_zoom', sa.Boolean(), server_default='1', nullable=False))
    # Gros plan par défaut : gameplay à 56 % de l'écran au lieu de 32 %.
    op.execute("UPDATE editing_profiles SET layout = 'focus' WHERE layout = 'blur'")



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('jump_zoom')

