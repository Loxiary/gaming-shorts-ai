"""initial schema: projects, jobs, job_steps, worker_heartbeats

Revision ID: 0001
Revises: 
Create Date: 2026-11-10 20:46:56.802026

Dates stockées en UTC naïf (conversion par app.models.base.UTCDateTime).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('projects',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('game', sa.String(length=120), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_test', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('length(trim(name)) > 0', name=op.f('ck_projects_name_not_empty')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_table('worker_heartbeats',
    sa.Column('worker_id', sa.String(length=120), nullable=False),
    sa.Column('hostname', sa.String(length=255), nullable=False),
    sa.Column('pid', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('worker_id', name=op.f('pk_worker_heartbeats'))
    )
    op.create_table('jobs',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('progress', sa.Float(), nullable=False),
    sa.Column('current_step', sa.String(length=80), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('cancel_requested', sa.Boolean(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('locked_by', sa.String(length=120), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name=op.f('ck_jobs_status_valid')),
    sa.CheckConstraint('progress >= 0 AND progress <= 1', name=op.f('ck_jobs_progress_range')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_jobs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_jobs'))
    )
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_jobs_project_id'), ['project_id'], unique=False)
        batch_op.create_index('ix_jobs_status_created_at', ['status', 'created_at'], unique=False)
        batch_op.create_index('uq_jobs_active_project_kind', ['project_id', 'kind'], unique=True, sqlite_where=sa.text("status IN ('queued', 'running')"))

    op.create_table('job_steps',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('job_id', sa.String(length=32), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name=op.f('ck_job_steps_status_valid')),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_job_steps_job_id_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_steps')),
    sa.UniqueConstraint('job_id', 'position', name='uq_job_steps_job_position')
    )
    with op.batch_alter_table('job_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_job_steps_job_id'), ['job_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('job_steps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_steps_job_id'))

    op.drop_table('job_steps')
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('uq_jobs_active_project_kind', sqlite_where=sa.text("status IN ('queued', 'running')"))
        batch_op.drop_index('ix_jobs_status_created_at')
        batch_op.drop_index(batch_op.f('ix_jobs_project_id'))

    op.drop_table('jobs')
    op.drop_table('worker_heartbeats')
    op.drop_table('projects')
