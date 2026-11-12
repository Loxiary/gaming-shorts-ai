"""Phase 2 : sources, transcriptions, progression des étapes

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10 21:19:59.193259
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('source_media',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('source_type', sa.String(length=20), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=False),
    sa.Column('rights_status', sa.String(length=20), nullable=False),
    sa.Column('rights_note', sa.Text(), nullable=True),
    sa.Column('title', sa.String(length=500), nullable=True),
    sa.Column('uploader', sa.String(length=300), nullable=True),
    sa.Column('channel_id', sa.String(length=100), nullable=True),
    sa.Column('channel_url', sa.String(length=500), nullable=True),
    sa.Column('upload_date', sa.String(length=8), nullable=True),
    sa.Column('platform_license', sa.String(length=200), nullable=True),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('metadata_json', sa.Text(), nullable=True),
    sa.Column('media_path', sa.String(length=500), nullable=True),
    sa.Column('media_size_bytes', sa.Integer(), nullable=True),
    sa.Column('audio_path', sa.String(length=500), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('fps', sa.Float(), nullable=True),
    sa.Column('video_codec', sa.String(length=50), nullable=True),
    sa.Column('audio_codec', sa.String(length=50), nullable=True),
    sa.Column('has_audio', sa.Boolean(), nullable=True),
    sa.Column('probe_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("rights_status IN ('unknown', 'owned', 'authorized', 'licensed')", name=op.f('ck_source_media_rights_status_valid')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_source_media_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_media')),
    sa.UniqueConstraint('project_id', name=op.f('uq_source_media_project_id')),
    sa.UniqueConstraint('source_type', 'external_id', name='uq_source_media_type_external')
    )
    op.create_table('transcripts',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('source_media_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('engine', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('device', sa.String(length=20), nullable=False),
    sa.Column('compute_type', sa.String(length=30), nullable=False),
    sa.Column('language', sa.String(length=10), nullable=True),
    sa.Column('language_probability', sa.Float(), nullable=True),
    sa.Column('audio_duration_seconds', sa.Float(), nullable=True),
    sa.Column('processing_seconds', sa.Float(), nullable=True),
    sa.Column('options_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['source_media_id'], ['source_media.id'], name=op.f('fk_transcripts_source_media_id_source_media'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transcripts'))
    )
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transcripts_source_media_id'), ['source_media_id'], unique=False)

    op.create_table('transcript_segments',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('transcript_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('avg_logprob', sa.Float(), nullable=True),
    sa.Column('no_speech_prob', sa.Float(), nullable=True),
    sa.Column('words_json', sa.Text(), nullable=True),
    sa.CheckConstraint('end_seconds >= start_seconds', name=op.f('ck_transcript_segments_segment_order')),
    sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], name=op.f('fk_transcript_segments_transcript_id_transcripts'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transcript_segments')),
    sa.UniqueConstraint('transcript_id', 'position', name='uq_transcript_segments_position')
    )
    with op.batch_alter_table('transcript_segments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transcript_segments_transcript_id'), ['transcript_id'], unique=False)

    with op.batch_alter_table('job_steps', schema=None) as batch_op:
        # server_default : les étapes existantes (Phase 1) reçoivent 0.
        batch_op.add_column(sa.Column('progress', sa.Float(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('detail', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('output_json', sa.Text(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('job_steps', schema=None) as batch_op:
        batch_op.drop_column('output_json')
        batch_op.drop_column('detail')
        batch_op.drop_column('progress')

    with op.batch_alter_table('transcript_segments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transcript_segments_transcript_id'))

    op.drop_table('transcript_segments')
    with op.batch_alter_table('transcripts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transcripts_source_media_id'))

    op.drop_table('transcripts')
    op.drop_table('source_media')
