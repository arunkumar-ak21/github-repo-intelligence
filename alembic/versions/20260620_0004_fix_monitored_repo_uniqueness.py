"""fix monitored repository tenant-aware uniqueness

Revision ID: 20260620_0004
Revises: 20260617_0003
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260620_0004"
down_revision = "20260617_0003"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "monitored_repositories" not in tables:
        return

    # Old migration 0002 created a global unique index on full_name.  That is
    # wrong for a multi-tenant product and also breaks repeated GitHub App syncs
    # for legacy rows that were created before tenant_id existed.
    if _index_exists("monitored_repositories", "ix_monitored_repositories_full_name"):
        op.drop_index("ix_monitored_repositories_full_name", table_name="monitored_repositories")

    columns = {column["name"] for column in inspector.get_columns("monitored_repositories")}
    if "tenant_id" in columns:
        # Local MVP repair: rows created before tenancy should belong to the
        # first available tenant so the upsert can adopt/update them cleanly.
        bind.execute(sa.text("""
            UPDATE monitored_repositories
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND EXISTS (SELECT 1 FROM tenants)
        """))

    if "setup_status" in columns:
        bind.execute(sa.text("""
            UPDATE monitored_repositories
            SET setup_status = 'pending'
            WHERE setup_status IS NULL OR setup_status = ''
        """))

    if not _index_exists("monitored_repositories", "ix_monitored_repositories_tenant_full_name"):
        op.create_index(
            "ix_monitored_repositories_tenant_full_name",
            "monitored_repositories",
            ["tenant_id", "full_name"],
            unique=True,
        )


def downgrade() -> None:
    if _index_exists("monitored_repositories", "ix_monitored_repositories_tenant_full_name"):
        op.drop_index("ix_monitored_repositories_tenant_full_name", table_name="monitored_repositories")
    if not _index_exists("monitored_repositories", "ix_monitored_repositories_full_name"):
        op.create_index(
            "ix_monitored_repositories_full_name",
            "monitored_repositories",
            ["full_name"],
            unique=True,
        )
