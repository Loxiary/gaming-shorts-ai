"""Phase 3 : profils de montage, analyses, scènes, candidats, scores, coûts API, réglages

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10 22:05:44.095847
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_usage',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=False),
    sa.Column('purpose', sa.String(length=50), nullable=False),
    sa.Column('project_id', sa.String(length=32), nullable=True),
    sa.Column('job_id', sa.String(length=32), nullable=True),
    sa.Column('candidate_id', sa.String(length=32), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
    sa.Column('images', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('request_id', sa.String(length=100), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_usage'))
    )
    with op.batch_alter_table('api_usage', schema=None) as batch_op:
        batch_op.create_index('ix_api_usage_created_at', ['created_at'], unique=False)

    op.create_table('app_settings',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('value_json', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('editing_profiles',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('editorial_focus', sa.Text(), nullable=True),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('weights_json', sa.Text(), nullable=False),
    sa.Column('output_language', sa.String(length=10), nullable=False),
    sa.Column('min_duration', sa.Float(), nullable=False),
    sa.Column('max_duration', sa.Float(), nullable=False),
    sa.Column('max_candidates', sa.Integer(), nullable=False),
    sa.Column('use_vision', sa.Boolean(), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('max_candidates >= 1 AND max_candidates <= 50', name=op.f('ck_editing_profiles_max_candidates')),
    sa.CheckConstraint('min_duration >= 61.0 AND max_duration <= 180.0 AND min_duration <= max_duration', name=op.f('ck_editing_profiles_duration_bounds')),
    sa.CheckConstraint('threshold >= 0 AND threshold <= 100', name=op.f('ck_editing_profiles_threshold_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_editing_profiles')),
    sa.UniqueConstraint('name', name=op.f('uq_editing_profiles_name'))
    )
    op.create_table('clip_analyses',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('job_id', sa.String(length=32), nullable=True),
    sa.Column('profile_id', sa.String(length=32), nullable=True),
    sa.Column('profile_snapshot_json', sa.Text(), nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('engine', sa.String(length=20), nullable=True),
    sa.Column('llm_model', sa.String(length=80), nullable=True),
    sa.Column('use_vision', sa.Boolean(), nullable=False),
    sa.Column('signals_path', sa.String(length=500), nullable=True),
    sa.Column('notes_json', sa.Text(), nullable=True),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_clip_analyses_job_id_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['profile_id'], ['editing_profiles.id'], name=op.f('fk_clip_analyses_profile_id_editing_profiles'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_clip_analyses_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clip_analyses'))
    )
    with op.batch_alter_table('clip_analyses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clip_analyses_project_id'), ['project_id'], unique=False)

    op.create_table('scene_segments',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('source_media_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('cut_score', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['source_media_id'], ['source_media.id'], name=op.f('fk_scene_segments_source_media_id_source_media'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scene_segments')),
    sa.UniqueConstraint('source_media_id', 'position', name='uq_scene_segments_position')
    )
    with op.batch_alter_table('scene_segments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_scene_segments_source_media_id'), ['source_media_id'], unique=False)

    op.create_table('clip_candidates',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('analysis_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('peak_seconds', sa.Float(), nullable=True),
    sa.Column('signal_score', sa.Float(), nullable=False),
    sa.Column('signals_json', sa.Text(), nullable=True),
    sa.Column('transcript_excerpt', sa.Text(), nullable=True),
    sa.Column('frames_json', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('events_json', sa.Text(), nullable=True),
    sa.Column('warnings_json', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('overall_score', sa.Float(), nullable=True),
    sa.Column('selected', sa.Boolean(), nullable=False),
    sa.Column('rejection_reason', sa.String(length=200), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('llm_model', sa.String(length=80), nullable=True),
    sa.Column('raw_response_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('end_seconds - start_seconds >= 60.999 AND end_seconds - start_seconds <= 180.001', name=op.f('ck_clip_candidates_duration_61_180')),
    sa.ForeignKeyConstraint(['analysis_id'], ['clip_analyses.id'], name=op.f('fk_clip_candidates_analysis_id_clip_analyses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clip_candidates')),
    sa.UniqueConstraint('analysis_id', 'position', name='uq_clip_candidates_position')
    )
    with op.batch_alter_table('clip_candidates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clip_candidates_analysis_id'), ['analysis_id'], unique=False)

    op.create_table('clip_scores',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('candidate_id', sa.String(length=32), nullable=False),
    sa.Column('criterion', sa.String(length=30), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('justification', sa.Text(), nullable=True),
    sa.CheckConstraint('score >= 0 AND score <= 10', name=op.f('ck_clip_scores_score_range')),
    sa.ForeignKeyConstraint(['candidate_id'], ['clip_candidates.id'], name=op.f('fk_clip_scores_candidate_id_clip_candidates'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clip_scores')),
    sa.UniqueConstraint('candidate_id', 'criterion', name='uq_clip_scores_criterion')
    )
    with op.batch_alter_table('clip_scores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clip_scores_candidate_id'), ['candidate_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('clip_scores', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clip_scores_candidate_id'))

    op.drop_table('clip_scores')
    with op.batch_alter_table('clip_candidates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clip_candidates_analysis_id'))

    op.drop_table('clip_candidates')
    with op.batch_alter_table('scene_segments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_scene_segments_source_media_id'))

    op.drop_table('scene_segments')
    with op.batch_alter_table('clip_analyses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clip_analyses_project_id'))

    op.drop_table('clip_analyses')
    op.drop_table('editing_profiles')
    op.drop_table('app_settings')
    with op.batch_alter_table('api_usage', schema=None) as batch_op:
        batch_op.drop_index('ix_api_usage_created_at')

    op.drop_table('api_usage')
