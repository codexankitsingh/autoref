"""add_scraped_jobs_table_and_message_tracking_columns

Revision ID: 8eb55f723083
Revises: 
Create Date: 2026-05-25 16:18:26.310080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8eb55f723083'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table (safe for both SQLite and PostgreSQL)."""
    from alembic import op
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def _table_exists(table_name: str) -> bool:
    """Check if a table already exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # ── 1. Create scraped_jobs table (Phase 1: Job Discovery) ──
    if not _table_exists("scraped_jobs"):
        op.create_table('scraped_jobs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('job_url', sa.String(length=1024), nullable=True),
            sa.Column('job_url_hash', sa.String(length=64), nullable=True),
            sa.Column('title', sa.String(length=500), nullable=True),
            sa.Column('company', sa.String(length=255), nullable=True),
            sa.Column('company_domain', sa.String(length=255), nullable=True),
            sa.Column('location', sa.String(length=500), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('source', sa.String(length=50), nullable=True),
            sa.Column('match_score', sa.Integer(), nullable=True),
            sa.Column('match_reason', sa.Text(), nullable=True),
            sa.Column('missing_skills', sa.Text(), nullable=True),
            sa.Column('required_skills', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=50), nullable=True),
            sa.Column('scraped_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('scored_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(op.f('ix_scraped_jobs_job_url_hash'), 'scraped_jobs', ['job_url_hash'], unique=True)

    # ── 2. Add email open tracking columns to messages (Phase 2) ──
    if not _column_exists("messages", "tracking_id"):
        op.add_column('messages', sa.Column('tracking_id', sa.String(length=64), nullable=True))
    if not _column_exists("messages", "open_count"):
        op.add_column('messages', sa.Column('open_count', sa.Integer(), nullable=True))
    if not _column_exists("messages", "opened_at"):
        op.add_column('messages', sa.Column('opened_at', sa.DateTime(), nullable=True))
    if not _column_exists("messages", "last_opened_at"):
        op.add_column('messages', sa.Column('last_opened_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Drop tracking columns from messages
    op.drop_column('messages', 'last_opened_at')
    op.drop_column('messages', 'opened_at')
    op.drop_column('messages', 'open_count')
    op.drop_column('messages', 'tracking_id')
    # Drop scraped_jobs table
    op.drop_index(op.f('ix_scraped_jobs_job_url_hash'), table_name='scraped_jobs')
    op.drop_table('scraped_jobs')
