"""Pydantic schemas for autonomous pipeline report ingestion."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QualitySummary(BaseModel):
    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    files_scanned: int = 0
    duration_seconds: float = 0.0


class QualityArtifactLinks(BaseModel):
    json_report: str | None = None
    html_report: str | None = None
    github_artifact: str | None = None


class QualityFinding(BaseModel):
    scanner: str | None = None
    severity: str | None = None
    rule_id: str | None = None
    title: str | None = None
    message: str | None = None
    file_path: str | None = None
    line_number: int | None = None
    recommendation: str | None = None


class QualityReportPayload(BaseModel):
    repo: str = Field(..., examples=["owner/repo"])
    branch: str
    commit_sha: str
    pr_number: int | None = None
    workflow_run_id: str
    workflow_url: str | None = None

    stage: Literal["quality_gate"] = "quality_gate"
    status_check: str = "quality-gate"

    verdict: Literal["pass", "warn", "fail", "error"]
    status: Literal["passed", "failed", "blocked", "error"]
    blocking: bool

    started_at: str | None = None
    finished_at: str | None = None

    summary: QualitySummary = Field(default_factory=QualitySummary)
    findings: list[QualityFinding] = Field(default_factory=list)
    artifacts: QualityArtifactLinks = Field(default_factory=QualityArtifactLinks)

    raw_report: dict[str, Any] = Field(default_factory=dict)


class PipelineStagePayload(BaseModel):
    stage: Literal[
        "quality_gate",
        "compiler_check",
        "ai_remediation",
        "final_verification",
        "repo_intelligence",
    ]
    status: Literal[
        "pending",
        "running",
        "passed",
        "failed",
        "blocked",
        "error",
        "skipped",
        "needs_human",
    ]
    blocking: bool = False
    repo: str
    branch: str | None = None
    commit_sha: str
    pr_number: int | None = None
    workflow_run_id: str
    workflow_url: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    next_stage: str | None = None
    errors: list[dict[str, Any] | str] = Field(default_factory=list)
    raw_report: dict[str, Any] = Field(default_factory=dict)
