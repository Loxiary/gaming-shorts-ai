"""Phase 4 : réglages de montage des profils, rendus de shorts

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11 14:44:03.131873
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('clip_renders',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('candidate_id', sa.String(length=32), nullable=True),
    sa.Column('job_id', sa.String(length=32), nullable=True),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('profile_snapshot_json', sa.Text(), nullable=False),
    sa.Column('candidate_snapshot_json', sa.Text(), nullable=True),
    sa.Column('plan_json', sa.Text(), nullable=True),
    sa.Column('plan_engine', sa.String(length=20), nullable=True),
    sa.Column('subtitles_json', sa.Text(), nullable=True),
    sa.Column('subtitle_language', sa.String(length=10), nullable=True),
    sa.Column('subtitles_are_translation', sa.Boolean(), nullable=False),
    sa.Column('output_path', sa.String(length=500), nullable=True),
    sa.Column('output_size_bytes', sa.Integer(), nullable=True),
    sa.Column('qc_json', sa.Text(), nullable=True),
    sa.Column('qc_passed', sa.Boolean(), nullable=True),
    sa.Column('risk_report_json', sa.Text(), nullable=True),
    sa.Column('cost_usd', sa.Float(), nullable=False),
    sa.Column('export_status', sa.String(length=20), nullable=False),
    sa.Column('exported_path', sa.String(length=500), nullable=True),
    sa.Column('export_confirmed_at', sa.DateTime(), nullable=True),
    sa.Column('acknowledged_warnings_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['clip_candidates.id'], name=op.f('fk_clip_renders_candidate_id_clip_candidates'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_clip_renders_job_id_jobs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_clip_renders_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clip_renders'))
    )
    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clip_renders_candidate_id'), ['candidate_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_clip_renders_project_id'), ['project_id'], unique=False)

    # Plusieurs montages peuvent attendre dans la file pour un même projet :
    # l'anti-doublon par (projet, type) ne s'applique plus aux jobs « render_clip ».
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('uq_jobs_active_project_kind')
        batch_op.create_index('uq_jobs_active_project_kind', ['project_id', 'kind'], unique=True,
                              sqlite_where=sa.text("status IN ('queued', 'running') AND kind != 'render_clip'"))

    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subtitle_mode', sa.String(length=20), server_default='source', nullable=False))
        batch_op.add_column(sa.Column('subtitle_style_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('layout', sa.String(length=20), server_default='blur', nullable=False))
        batch_op.add_column(sa.Column('zoom_intensity', sa.Float(), server_default='0.12', nullable=False))
        batch_op.add_column(sa.Column('hook_enabled', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('cta_enabled', sa.Boolean(), server_default='1', nullable=False))
        batch_op.add_column(sa.Column('cta_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('render_encoder', sa.String(length=20), server_default='libx264', nullable=False))
        batch_op.create_check_constraint(
            op.f('ck_editing_profiles_zoom_range'), 'zoom_intensity >= 0 AND zoom_intensity <= 0.5'
        )



def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('uq_jobs_active_project_kind')
        batch_op.create_index('uq_jobs_active_project_kind', ['project_id', 'kind'], unique=True,
                              sqlite_where=sa.text("status IN ('queued', 'running')"))

    with op.batch_alter_table('editing_profiles', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_editing_profiles_zoom_range'), type_='check')
        batch_op.drop_column('render_encoder')
        batch_op.drop_column('cta_text')
        batch_op.drop_column('cta_enabled')
        batch_op.drop_column('hook_enabled')
        batch_op.drop_column('zoom_intensity')
        batch_op.drop_column('layout')
        batch_op.drop_column('subtitle_style_json')
        batch_op.drop_column('subtitle_mode')

    with op.batch_alter_table('clip_renders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_clip_renders_project_id'))
        batch_op.drop_index(batch_op.f('ix_clip_renders_candidate_id'))

    op.drop_table('clip_renders')
