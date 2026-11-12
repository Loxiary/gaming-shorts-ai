"""Phase 5 : réglages audio et facecam des profils, bibliothèque musicale, rapports audio

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11 16:04:10.077647
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('music_tracks',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=True),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('artist', sa.String(length=300), nullable=True),
    sa.Column('license', sa.String(length=300), nullable=True),
    sa.Column('source_url', sa.String(length=500), nullable=True),
    sa.Column('moods', sa.String(length=300), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('license_confirmed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_music_tracks')),
    sa.UniqueConstraint('file_path', name=op.f('uq_music_tracks_file_path'))
    )
    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('audio_report_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('facecam_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('credits_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('preview_audio_path', sa.String(length=500), nullable=True))

    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('narration_mode', sa.String(length=20), server_default='auto', nullable=False))
        batch_op.add_column(sa.Column('narration_voice', sa.String(length=60), server_default='fr_FR-siwis-medium', nullable=False))
        batch_op.add_column(sa.Column('narration_speed', sa.Float(), server_default='1.0', nullable=False))
        batch_op.add_column(sa.Column('narration_level_db', sa.Float(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('game_level_db', sa.Float(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('music_mode', sa.String(length=20), server_default='library', nullable=False))
        batch_op.add_column(sa.Column('music_level_db', sa.Float(), server_default='-18', nullable=False))
        batch_op.add_column(sa.Column('source_music_mode', sa.String(length=20), server_default='attenuate', nullable=False))
        batch_op.add_column(sa.Column('source_music_reduction_db', sa.Float(), server_default='15', nullable=False))
        batch_op.add_column(sa.Column('facecam_mode', sa.String(length=20), server_default='crop', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_column('facecam_mode')
        batch_op.drop_column('source_music_reduction_db')
        batch_op.drop_column('source_music_mode')
        batch_op.drop_column('music_level_db')
        batch_op.drop_column('music_mode')
        batch_op.drop_column('game_level_db')
        batch_op.drop_column('narration_level_db')
        batch_op.drop_column('narration_speed')
        batch_op.drop_column('narration_voice')
        batch_op.drop_column('narration_mode')

    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.drop_column('preview_audio_path')
        batch_op.drop_column('credits_json')
        batch_op.drop_column('facecam_json')
        batch_op.drop_column('audio_report_json')

    op.drop_table('music_tracks')
