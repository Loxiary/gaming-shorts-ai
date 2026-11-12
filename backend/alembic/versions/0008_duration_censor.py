"""Durée maximale des shorts ramenée à 90 s, censure des mots grossiers (profils)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-11 19:24:56.806463
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('censor_profanity', sa.Boolean(), server_default='1', nullable=False))
    # Profils existants ramenés dans la nouvelle plage 61–90 s.
    op.execute("UPDATE editing_profiles SET max_duration = 90 WHERE max_duration > 90")
    op.execute("UPDATE editing_profiles SET min_duration = 61 WHERE min_duration > 90")



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('censor_profanity')

