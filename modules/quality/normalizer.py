"""Normalize quality and pipeline reports before database storage."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from core.config import settings
from modules.quality.schemas import PipelineStagePayload, QualityFinding, QualityReportPayload
from modules.security.sanitizer import sanitize_finding, sanitize_payload


SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def normalize_repo_name(repo: str) -> str:
    value = (repo or "").strip().strip("/")
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", value):
        raise ValueError("Repository must be in owner/repo format.")
    return value


def split_repo(repo: str) -> tuple[str, str]:
    normalized = normalize_repo_name(repo)
    owner, name = normalized.split("/", 1)
    return owner, name


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def duration_ms_from_payload(started_at: str | None, finished_at: str | None) -> int | None:
    started = parse_datetime(started_at)
    finished = parse_datetime(finished_at)
    if not started or not finished:
        return None
    return max(0, int((finished - started).total_seconds() * 1000))


def cap_and_sanitize_findings(findings: list[QualityFinding | dict[str, Any]]) -> list[dict[str, Any]]:
    raw_findings = [
        finding.model_dump(mode="json") if hasattr(finding, "model_dump") else dict(finding)
        for finding in findings
    ]
    raw_findings.sort(key=lambda item: SEVERITY_RANK.get(str(item.get("severity", "")).lower(), 99))
    capped = raw_findings[: settings.MAX_FINDINGS_PER_REPORT]
    return [sanitize_finding(item) for item in capped]


def quality_payload_to_stage(payload: QualityReportPayload) -> PipelineStagePayload:
    duration_ms = duration_ms_from_payload(payload.started_at, payload.finished_at)
    if duration_ms is None:
        duration_ms = int(payload.summary.duration_seconds * 1000)

    return PipelineStagePayload(
        stage=payload.stage,
        status=payload.status,
        blocking=payload.blocking,
        repo=payload.repo,
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        pr_number=payload.pr_number,
        workflow_run_id=payload.workflow_run_id,
        workflow_url=payload.workflow_url,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
        duration_ms=duration_ms,
        summary=payload.summary.model_dump(mode="json"),
        findings=cap_and_sanitize_findings(payload.findings),
        artifacts=payload.artifacts.model_dump(mode="json"),
        next_stage="compiler_check" if not payload.blocking else None,
        errors=[],
        raw_report=sanitize_payload(payload.raw_report),
    )


def run_status_from_stage(stage: PipelineStagePayload) -> str:
    if stage.status in {"failed", "blocked", "error", "needs_human"}:
        return stage.status
    if stage.stage == "compiler_check" and stage.status == "passed":
        return "completed"
    if stage.stage == "final_verification" and stage.status == "passed":
        return "completed"
    return "running"
