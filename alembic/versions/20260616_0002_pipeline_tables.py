"""add autonomous pipeline tables

Revision ID: 20260616_0002
Revises: 20260612_0001
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260616_0002"
down_revision = "20260612_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=False),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("workflow_run_id", sa.String(), nullable=False),
        sa.Column("overall_status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "repo",
            "commit_sha",
            "workflow_run_id",
            name="uq_pipeline_run_identity",
        ),
    )
    op.create_index("ix_pipeline_runs_id", "pipeline_runs", ["id"])
    op.create_index("ix_pipeline_runs_repo", "pipeline_runs", ["repo"])
    op.create_index("ix_pipeline_runs_branch", "pipeline_runs", ["branch"])
    op.create_index("ix_pipeline_runs_commit_sha", "pipeline_runs", ["commit_sha"])
    op.create_index("ix_pipeline_runs_workflow_run_id", "pipeline_runs", ["workflow_run_id"])
    op.create_index("ix_pipeline_runs_overall_status", "pipeline_runs", ["overall_status"])

    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("artifacts_json", sa.JSON(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.UniqueConstraint(
            "pipeline_run_id",
            "stage_name",
            name="uq_pipeline_stage_identity",
        ),
    )
    op.create_index("ix_pipeline_stages_id", "pipeline_stages", ["id"])
    op.create_index("ix_pipeline_stages_pipeline_run_id", "pipeline_stages", ["pipeline_run_id"])
    op.create_index("ix_pipeline_stages_stage_name", "pipeline_stages", ["stage_name"])
    op.create_index("ix_pipeline_stages_status", "pipeline_stages", ["status"])

    op.create_table(
        "quality_findings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("pipeline_stage_id", sa.Integer(), nullable=False),
        sa.Column("scanner", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("rule_id", sa.String(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_stage_id"], ["pipeline_stages.id"]),
    )
    op.create_index("ix_quality_findings_id", "quality_findings", ["id"])
    op.create_index("ix_quality_findings_pipeline_stage_id", "quality_findings", ["pipeline_stage_id"])
    op.create_index("ix_quality_findings_scanner", "quality_findings", ["scanner"])
    op.create_index("ix_quality_findings_severity", "quality_findings", ["severity"])
    op.create_index("ix_quality_findings_rule_id", "quality_findings", ["rule_id"])

    op.create_table(
        "monitored_repositories",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("repo", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_monitored_repositories_id", "monitored_repositories", ["id"])
    op.create_index(
        "ix_monitored_repositories_full_name",
        "monitored_repositories",
        ["full_name"],
        unique=True,
    )
    op.create_index("ix_monitored_repositories_owner", "monitored_repositories", ["owner"])
    op.create_index("ix_monitored_repositories_repo", "monitored_repositories", ["repo"])


def downgrade() -> None:
    op.drop_index("ix_monitored_repositories_repo", table_name="monitored_repositories")
    op.drop_index("ix_monitored_repositories_owner", table_name="monitored_repositories")
    op.drop_index("ix_monitored_repositories_full_name", table_name="monitored_repositories")
    op.drop_index("ix_monitored_repositories_id", table_name="monitored_repositories")
    op.drop_table("monitored_repositories")

    op.drop_index("ix_quality_findings_rule_id", table_name="quality_findings")
    op.drop_index("ix_quality_findings_severity", table_name="quality_findings")
    op.drop_index("ix_quality_findings_scanner", table_name="quality_findings")
    op.drop_index("ix_quality_findings_pipeline_stage_id", table_name="quality_findings")
    op.drop_index("ix_quality_findings_id", table_name="quality_findings")
    op.drop_table("quality_findings")

    op.drop_index("ix_pipeline_stages_status", table_name="pipeline_stages")
    op.drop_index("ix_pipeline_stages_stage_name", table_name="pipeline_stages")
    op.drop_index("ix_pipeline_stages_pipeline_run_id", table_name="pipeline_stages")
    op.drop_index("ix_pipeline_stages_id", table_name="pipeline_stages")
    op.drop_table("pipeline_stages")

    op.drop_index("ix_pipeline_runs_overall_status", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_workflow_run_id", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_commit_sha", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_branch", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_repo", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
