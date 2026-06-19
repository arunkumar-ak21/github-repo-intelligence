"""add repository ignore and deprovision fields

Revision ID: 20260620_0005
Revises: 20260620_0004
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260620_0005"
down_revision = "20260620_0004"
branch_labels = None
depends_on = None


_TABLE = "monitored_repositories"


def _existing_columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {column["name"] for column in inspector.get_columns(_TABLE)}
    except Exception:
        return set()


def _add_column_if_missing(name: str, column: sa.Column) -> None:
    if name not in _existing_columns():
        op.add_column(_TABLE, column)


def upgrade() -> None:
    _add_column_if_missing("ignored_at", sa.Column("ignored_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("deprovisioned_at", sa.Column("deprovisioned_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("setup_pr_number", sa.Column("setup_pr_number", sa.Integer(), nullable=True))
    _add_column_if_missing("setup_pr_url", sa.Column("setup_pr_url", sa.Text(), nullable=True))
    _add_column_if_missing("setup_pr_branch", sa.Column("setup_pr_branch", sa.String(), nullable=True))
    _add_column_if_missing("cleanup_pr_number", sa.Column("cleanup_pr_number", sa.Integer(), nullable=True))
    _add_column_if_missing("cleanup_pr_url", sa.Column("cleanup_pr_url", sa.Text(), nullable=True))
    _add_column_if_missing("cleanup_pr_branch", sa.Column("cleanup_pr_branch", sa.String(), nullable=True))
    _add_column_if_missing("last_sync_at", sa.Column("last_sync_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("last_deprovision_error", sa.Column("last_deprovision_error", sa.Text(), nullable=True))


def downgrade() -> None:
    existing = _existing_columns()
    for name in [
        "last_deprovision_error",
        "last_sync_at",
        "cleanup_pr_branch",
        "cleanup_pr_url",
        "cleanup_pr_number",
        "setup_pr_branch",
        "setup_pr_url",
        "setup_pr_number",
        "deprovisioned_at",
        "ignored_at",
    ]:
        if name in existing:
            op.drop_column(_TABLE, name)
