"""Titre permanent lu par la voix, bip, confiance minimale, musique conseillée, publication

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-11 23:30:27.734209
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('publication_json', sa.Text(), nullable=True))

    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bleep_profanity', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('narration_title', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('min_confidence', sa.Float(), server_default='0.5', nullable=False))

    # Musique : conseillée à l'upload (bibliothèque de la plateforme) plutôt qu'incrustée.
    op.execute("UPDATE editing_profiles SET music_mode = 'suggest' WHERE music_mode = 'library'")
    # Seuils recalibrés (la notation ne pénalise plus grossièretés, HUD, transcription, contexte).
    op.execute(
        "UPDATE editing_profiles SET threshold = 55 "
        "WHERE name = 'GTA 6 — Viral' AND threshold > 55"
    )
    op.execute(
        "UPDATE editing_profiles SET threshold = 50 WHERE name IN "
        "('GTA 6 — Humour', 'GTA 6 — Action', 'Gaming — Immersion', 'Gaming — Histoire') "
        "AND threshold > 50"
    )



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('min_confidence')
        batch_op.drop_column('narration_title')
        batch_op.drop_column('bleep_profanity')

    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.drop_column('publication_json')

