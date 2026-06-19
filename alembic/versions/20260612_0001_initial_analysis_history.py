"""initial analysis history and metadata tables

Revision ID: 20260612_0001
Revises:
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260612_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("health_score", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("cicd_json", sa.JSON(), nullable=True),
        sa.Column("dependencies_json", sa.JSON(), nullable=True),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=True),
        sa.Column("forks", sa.Integer(), nullable=True),
        sa.Column("open_issues", sa.Integer(), nullable=True),
        sa.Column("default_branch", sa.String(), nullable=True),
        sa.Column("license_name", sa.String(), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("cicd_platforms", sa.JSON(), nullable=True),
        sa.Column("total_dependencies", sa.Integer(), nullable=True),
        sa.Column("vulnerable_count", sa.Integer(), nullable=True),
        sa.Column("outdated_count", sa.Integer(), nullable=True),
        sa.Column("analysis_duration_ms", sa.Integer(), nullable=True),
    )
    op.create_index("ix_analysis_history_id", "analysis_history", ["id"])
    op.create_index("ix_analysis_history_repo", "analysis_history", ["repo"])

    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("open_issues", sa.Integer(), nullable=False),
        sa.Column("readme", sa.Text(), nullable=True),
        sa.Column("topics", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(length=100), nullable=True),
        sa.Column("license_name", sa.String(length=100), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"], unique=True)
    op.create_index("ix_repositories_id", "repositories", ["id"])
    op.create_index("ix_repositories_name", "repositories", ["name"])
    op.create_index("ix_repositories_owner", "repositories", ["owner"])

    op.create_table(
        "commits",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("commit_hash", sa.String(length=40), nullable=False),
        sa.Column("author_name", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
    )
    op.create_index("ix_commits_commit_hash", "commits", ["commit_hash"])
    op.create_index("ix_commits_id", "commits", ["id"])

    op.create_table(
        "contributors",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("profile_url", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
        sa.Column("total_commits", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
    )
    op.create_index("ix_contributors_id", "contributors", ["id"])
    op.create_index("ix_contributors_username", "contributors", ["username"])

    op.create_table(
        "file_trees",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=False),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
    )
    op.create_index("ix_file_trees_id", "file_trees", ["id"])


def downgrade() -> None:
    op.drop_index("ix_file_trees_id", table_name="file_trees")
    op.drop_table("file_trees")
    op.drop_index("ix_contributors_username", table_name="contributors")
    op.drop_index("ix_contributors_id", table_name="contributors")
    op.drop_table("contributors")
    op.drop_index("ix_commits_id", table_name="commits")
    op.drop_index("ix_commits_commit_hash", table_name="commits")
    op.drop_table("commits")
    op.drop_index("ix_repositories_owner", table_name="repositories")
    op.drop_index("ix_repositories_name", table_name="repositories")
    op.drop_index("ix_repositories_id", table_name="repositories")
    op.drop_index("ix_repositories_full_name", table_name="repositories")
    op.drop_table("repositories")
    op.drop_index("ix_analysis_history_repo", table_name="analysis_history")
    op.drop_index("ix_analysis_history_id", table_name="analysis_history")
    op.drop_table("analysis_history")
