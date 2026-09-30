"""user prefs, thread context, recipient user scope

Revision ID: a1b2c3d4e5f6
Revises: 8eb55f723083
Create Date: 2026-09-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "8eb55f723083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    if not _column_exists("users", "default_target_role"):
        op.add_column(
            "users",
            sa.Column("default_target_role", sa.String(64), nullable=False, server_default="Data Engineering"),
        )
    if not _column_exists("users", "default_follow_up_interval_days"):
        op.add_column(
            "users",
            sa.Column("default_follow_up_interval_days", sa.Integer(), nullable=False, server_default="3"),
        )
    if not _column_exists("users", "default_max_follow_ups"):
        op.add_column(
            "users",
            sa.Column("default_max_follow_ups", sa.Integer(), nullable=False, server_default="3"),
        )
    if not _column_exists("users", "default_ai_model"):
        op.add_column(
            "users",
            sa.Column("default_ai_model", sa.String(64), nullable=False, server_default="gemini-2.5-flash-lite"),
        )

    if not _column_exists("job_applications", "target_role"):
        op.add_column("job_applications", sa.Column("target_role", sa.String(64), nullable=True))

    if not _column_exists("email_threads", "target_role"):
        op.add_column("email_threads", sa.Column("target_role", sa.String(64), nullable=True))

    if not _column_exists("recipients", "user_id"):
        op.add_column("recipients", sa.Column("user_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_recipients_user_id",
            "recipients",
            "users",
            ["user_id"],
            ["id"],
        )


def downgrade() -> None:
    if _column_exists("recipients", "user_id"):
        op.drop_constraint("fk_recipients_user_id", "recipients", type_="foreignkey")
        op.drop_column("recipients", "user_id")
    if _column_exists("email_threads", "target_role"):
        op.drop_column("email_threads", "target_role")
    if _column_exists("job_applications", "target_role"):
        op.drop_column("job_applications", "target_role")
    for col in (
        "default_ai_model",
        "default_max_follow_ups",
        "default_follow_up_interval_days",
        "default_target_role",
    ):
        if _column_exists("users", col):
            op.drop_column("users", col)
