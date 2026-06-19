"""add tenant foundation

Revision ID: 20260617_0003
Revises: 20260616_0002
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260617_0003"
down_revision = "20260616_0002"
branch_labels = None
depends_on = None


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column.name not in columns:
        op.add_column(table_name, column)


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("github_account_id", sa.Integer(), nullable=True),
        sa.Column("github_account_login", sa.String(), nullable=True),
        sa.Column("github_account_type", sa.String(), nullable=True),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tenants_id", "tenants", ["id"])
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenants_github_account_id", "tenants", ["github_account_id"])
    op.create_index("ix_tenants_github_account_login", "tenants", ["github_account_login"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("github_user_id", sa.Integer(), nullable=False),
        sa.Column("github_login", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_github_user_id", "users", ["github_user_id"], unique=True)
    op.create_index("ix_users_github_login", "users", ["github_login"], unique=True)

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership_identity"),
    )
    op.create_index("ix_tenant_memberships_id", "tenant_memberships", ["id"])
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])
    op.create_index("ix_tenant_memberships_role", "tenant_memberships", ["role"])

    op.create_table(
        "github_installations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("account_login", sa.String(), nullable=True),
        sa.Column("account_type", sa.String(), nullable=True),
        sa.Column("permissions_json", sa.JSON(), nullable=True),
        sa.Column("repository_selection", sa.String(), nullable=True),
        sa.Column("installed_at", sa.DateTime(), nullable=True),
        sa.Column("suspended_at", sa.DateTime(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_github_installations_id", "github_installations", ["id"])
    op.create_index("ix_github_installations_tenant_id", "github_installations", ["tenant_id"])
    op.create_index(
        "ix_github_installations_installation_id",
        "github_installations",
        ["installation_id"],
        unique=True,
    )
    op.create_index("ix_github_installations_account_id", "github_installations", ["account_id"])
    op.create_index("ix_github_installations_account_login", "github_installations", ["account_login"])

    _add_column_if_missing("analysis_history", sa.Column("tenant_id", sa.Integer(), nullable=True))
    _create_index_if_missing("analysis_history", "ix_analysis_history_tenant_id", ["tenant_id"])

    for table_name in ("repositories", "commits", "contributors", "file_trees"):
        _add_column_if_missing(table_name, sa.Column("tenant_id", sa.Integer(), nullable=True))
        _create_index_if_missing(table_name, f"ix_{table_name}_tenant_id", ["tenant_id"])
    _create_index_if_missing(
        "repositories",
        "ix_repositories_tenant_full_name",
        ["tenant_id", "full_name"],
        unique=True,
    )

    _add_column_if_missing("monitored_repositories", sa.Column("tenant_id", sa.Integer(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("installation_id", sa.Integer(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("default_branch", sa.String(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("setup_status", sa.String(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("workflow_installed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("secrets_configured_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("ruleset_configured_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("monitored_repositories", sa.Column("last_verified_at", sa.DateTime(), nullable=True))
    _create_index_if_missing("monitored_repositories", "ix_monitored_repositories_tenant_id", ["tenant_id"])
    _create_index_if_missing("monitored_repositories", "ix_monitored_repositories_installation_id", ["installation_id"])
    _create_index_if_missing("monitored_repositories", "ix_monitored_repositories_setup_status", ["setup_status"])
    _create_index_if_missing(
        "monitored_repositories",
        "ix_monitored_repositories_tenant_full_name",
        ["tenant_id", "full_name"],
        unique=True,
    )

    _add_column_if_missing("pipeline_runs", sa.Column("tenant_id", sa.Integer(), nullable=True))
    _add_column_if_missing("pipeline_runs", sa.Column("repository_id", sa.Integer(), nullable=True))
    _add_column_if_missing("pipeline_runs", sa.Column("workflow_url", sa.Text(), nullable=True))
    _create_index_if_missing("pipeline_runs", "ix_pipeline_runs_tenant_id", ["tenant_id"])
    _create_index_if_missing("pipeline_runs", "ix_pipeline_runs_repository_id", ["repository_id"])
    _create_index_if_missing(
        "pipeline_runs",
        "ix_pipeline_runs_tenant_repo_commit_workflow",
        ["tenant_id", "repo", "commit_sha", "workflow_run_id"],
        unique=True,
    )

    _add_column_if_missing("pipeline_stages", sa.Column("tenant_id", sa.Integer(), nullable=True))
    _create_index_if_missing("pipeline_stages", "ix_pipeline_stages_tenant_id", ["tenant_id"])

    _add_column_if_missing("quality_findings", sa.Column("tenant_id", sa.Integer(), nullable=True))
    _create_index_if_missing("quality_findings", "ix_quality_findings_tenant_id", ["tenant_id"])

    op.create_table(
        "repository_api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["monitored_repositories.id"]),
    )
    op.create_index("ix_repository_api_keys_id", "repository_api_keys", ["id"])
    op.create_index("ix_repository_api_keys_tenant_id", "repository_api_keys", ["tenant_id"])
    op.create_index("ix_repository_api_keys_repository_id", "repository_api_keys", ["repository_id"])
    op.create_index("ix_repository_api_keys_key_prefix", "repository_api_keys", ["key_prefix"])
    op.create_index("ix_repository_api_keys_key_hash", "repository_api_keys", ["key_hash"], unique=True)
    op.create_index("ix_repository_api_keys_status", "repository_api_keys", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_audit_events_id", "audit_events", ["id"])
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_target_type", "audit_events", ["target_type"])
    op.create_index("ix_audit_events_target_id", "audit_events", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_tenant_repo_commit_workflow", table_name="pipeline_runs")
    op.drop_index("ix_monitored_repositories_tenant_full_name", table_name="monitored_repositories")
    op.drop_index("ix_repositories_tenant_full_name", table_name="repositories")

    op.drop_index("ix_audit_events_target_id", table_name="audit_events")
    op.drop_index("ix_audit_events_target_type", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_index("ix_audit_events_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_repository_api_keys_status", table_name="repository_api_keys")
    op.drop_index("ix_repository_api_keys_key_hash", table_name="repository_api_keys")
    op.drop_index("ix_repository_api_keys_key_prefix", table_name="repository_api_keys")
    op.drop_index("ix_repository_api_keys_repository_id", table_name="repository_api_keys")
    op.drop_index("ix_repository_api_keys_tenant_id", table_name="repository_api_keys")
    op.drop_index("ix_repository_api_keys_id", table_name="repository_api_keys")
    op.drop_table("repository_api_keys")

    op.drop_index("ix_github_installations_account_login", table_name="github_installations")
    op.drop_index("ix_github_installations_account_id", table_name="github_installations")
    op.drop_index("ix_github_installations_installation_id", table_name="github_installations")
    op.drop_index("ix_github_installations_tenant_id", table_name="github_installations")
    op.drop_index("ix_github_installations_id", table_name="github_installations")
    op.drop_table("github_installations")

    op.drop_index("ix_tenant_memberships_role", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_user_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_tenant_id", table_name="tenant_memberships")
    op.drop_index("ix_tenant_memberships_id", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")

    op.drop_index("ix_users_github_login", table_name="users")
    op.drop_index("ix_users_github_user_id", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_tenants_github_account_login", table_name="tenants")
    op.drop_index("ix_tenants_github_account_id", table_name="tenants")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_index("ix_tenants_id", table_name="tenants")
    op.drop_table("tenants")
