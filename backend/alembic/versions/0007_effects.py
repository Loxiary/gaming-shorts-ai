"""Phase 7 : transitions et effets ponctuels (réglages de profil)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11 17:52:13.110557
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('effects_mode', sa.String(length=20), server_default='auto', nullable=False))
        batch_op.add_column(sa.Column('transition_in', sa.String(length=20), server_default='zoom', nullable=False))
        batch_op.add_column(sa.Column('transition_out', sa.String(length=20), server_default='fade', nullable=False))
        batch_op.add_column(sa.Column('sfx_mode', sa.String(length=20), server_default='auto', nullable=False))
        batch_op.add_column(sa.Column('sfx_level_db', sa.Float(), server_default='-14', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('sfx_level_db')
        batch_op.drop_column('sfx_mode')
        batch_op.drop_column('transition_out')
        batch_op.drop_column('transition_in')
        batch_op.drop_column('effects_mode')

