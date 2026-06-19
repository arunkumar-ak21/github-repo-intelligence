"""Database persistence for autonomous pipeline report ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from core.config import settings
from core.models import MonitoredRepository, PipelineRun, PipelineStage, QualityFinding, Tenant
from modules.tenancy.service import get_or_create_default_tenant, record_audit_event
from modules.quality.normalizer import (
    normalize_repo_name,
    parse_datetime,
    run_status_from_stage,
    split_repo,
)
from modules.quality.schemas import PipelineStagePayload
from modules.security.sanitizer import sanitize_payload


TERMINAL_RUN_STATUSES = {"completed", "failed", "blocked", "needs_human", "skipped", "error"}


class RepoNotAllowedError(ValueError):
    """Raised when a report arrives from an unregistered repository."""


def ensure_repo_allowed(db: Session, repo: str, tenant: Tenant | None = None) -> MonitoredRepository:
    tenant = tenant or get_or_create_default_tenant(db)
    normalized = normalize_repo_name(repo)
    record = (
        db.query(MonitoredRepository)
        .filter(
            MonitoredRepository.tenant_id == tenant.id,
            MonitoredRepository.full_name == normalized,
        )
        .first()
    )
    if record and record.is_active:
        return record

    if not settings.ALLOW_UNREGISTERED_REPOS:
        record_audit_event(
            db,
            tenant_id=tenant.id,
            event_type="report_repo_rejected",
            target_type="repository",
            target_id=normalized,
            metadata={"reason": "repository_not_monitored"},
        )
        raise RepoNotAllowedError(f"Repository '{normalized}' is not monitored.")

    owner, name = split_repo(normalized)
    if record:
        record.is_active = True
        record.setup_status = record.setup_status or "pending"
        return record

    record = MonitoredRepository(
        tenant_id=tenant.id,
        full_name=normalized,
        owner=owner,
        repo=name,
        setup_status="active" if settings.ALLOW_UNREGISTERED_REPOS else "pending",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    record_audit_event(
        db,
        tenant_id=tenant.id,
        event_type="repository_auto_registered",
        target_type="repository",
        target_id=normalized,
        metadata={"source": "report_ingestion_demo_mode"},
    )
    return record


def _get_or_create_run(
    db: Session,
    stage: PipelineStagePayload,
    raw_payload: dict[str, Any],
    repository: MonitoredRepository,
) -> PipelineRun:
    repo = normalize_repo_name(stage.repo)
    run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.tenant_id == repository.tenant_id,
            PipelineRun.repo == repo,
            PipelineRun.commit_sha == stage.commit_sha,
            PipelineRun.workflow_run_id == stage.workflow_run_id,
        )
        .first()
    )
    run_status = run_status_from_stage(stage)
    started_at = parse_datetime(stage.started_at)
    completed_at = parse_datetime(stage.finished_at)
    if run_status not in TERMINAL_RUN_STATUSES:
        completed_at = None

    raw_json = sanitize_payload(
        {
            "repo": repo,
            "branch": stage.branch,
            "commit_sha": stage.commit_sha,
            "pr_number": stage.pr_number,
            "workflow_run_id": stage.workflow_run_id,
            "workflow_url": stage.workflow_url,
            "latest_stage": stage.stage,
            "payload": raw_payload,
        }
    )

    if run:
        run.branch = stage.branch
        run.pr_number = stage.pr_number
        run.repository_id = repository.id
        run.workflow_url = stage.workflow_url
        run.overall_status = run_status
        run.started_at = run.started_at or started_at
        run.completed_at = completed_at
        run.raw_json = raw_json
        return run

    run = PipelineRun(
        tenant_id=repository.tenant_id,
        repository_id=repository.id,
        repo=repo,
        branch=stage.branch,
        commit_sha=stage.commit_sha,
        pr_number=stage.pr_number,
        workflow_run_id=stage.workflow_run_id,
        workflow_url=stage.workflow_url,
        overall_status=run_status,
        started_at=started_at,
        completed_at=completed_at,
        created_at=datetime.now(timezone.utc),
        raw_json=raw_json,
    )
    db.add(run)
    db.flush()
    return run


def _upsert_stage(
    db: Session,
    run: PipelineRun,
    stage: PipelineStagePayload,
    raw_payload: dict[str, Any],
) -> PipelineStage:
    stage_record = (
        db.query(PipelineStage)
        .filter(
            PipelineStage.pipeline_run_id == run.id,
            PipelineStage.stage_name == stage.stage,
        )
        .first()
    )
    started_at = parse_datetime(stage.started_at)
    completed_at = parse_datetime(stage.finished_at)
    raw_json = sanitize_payload(raw_payload)

    if stage_record is None:
        stage_record = PipelineStage(
            tenant_id=run.tenant_id,
            pipeline_run_id=run.id,
            stage_name=stage.stage,
            status=stage.status,
            blocking=stage.blocking,
        )
        db.add(stage_record)
        db.flush()

    stage_record.status = stage.status
    stage_record.blocking = stage.blocking
    stage_record.started_at = started_at
    stage_record.completed_at = completed_at
    stage_record.duration_ms = stage.duration_ms
    stage_record.summary_json = sanitize_payload(stage.summary)
    stage_record.artifacts_json = sanitize_payload(stage.artifacts)
    stage_record.raw_json = raw_json
    return stage_record


def _replace_stage_findings(
    db: Session,
    stage_record: PipelineStage,
    findings: list[dict[str, Any]],
) -> None:
    db.query(QualityFinding).filter(
        QualityFinding.pipeline_stage_id == stage_record.id
    ).delete(synchronize_session=False)

    for item in findings:
        db.add(
            QualityFinding(
                tenant_id=stage_record.tenant_id,
                pipeline_stage_id=stage_record.id,
                scanner=item.get("scanner"),
                severity=item.get("severity"),
                rule_id=item.get("rule_id"),
                title=item.get("title"),
                message=item.get("message"),
                file_path=item.get("file_path"),
                line_number=item.get("line_number"),
                recommendation=item.get("recommendation"),
                created_at=datetime.now(timezone.utc),
            )
        )


def upsert_stage_report(
    db: Session,
    stage: PipelineStagePayload,
    raw_payload: dict[str, Any],
    repository: MonitoredRepository | None = None,
) -> tuple[PipelineRun, PipelineStage]:
    if repository is None:
        tenant = get_or_create_default_tenant(db)
        repository = ensure_repo_allowed(db, stage.repo, tenant)
    run = _get_or_create_run(db, stage, raw_payload, repository)
    stage_record = _upsert_stage(db, run, stage, raw_payload)

    _replace_stage_findings(db, stage_record, stage.findings)

    db.commit()
    db.refresh(run)
    db.refresh(stage_record)
    return run, stage_record


def stage_to_dict(stage: PipelineStage) -> dict[str, Any]:
    return {
        "id": stage.id,
        "tenant_id": stage.tenant_id,
        "pipeline_run_id": stage.pipeline_run_id,
        "stage_name": stage.stage_name,
        "status": stage.status,
        "blocking": stage.blocking,
        "started_at": stage.started_at.isoformat() if stage.started_at else None,
        "completed_at": stage.completed_at.isoformat() if stage.completed_at else None,
        "duration_ms": stage.duration_ms,
        "summary": stage.summary_json or {},
        "artifacts": stage.artifacts_json or {},
    }


def run_to_dict(db: Session, run: PipelineRun, include_details: bool = False) -> dict[str, Any]:
    payload = {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "repository_id": run.repository_id,
        "repo": run.repo,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "pr_number": run.pr_number,
        "workflow_run_id": run.workflow_run_id,
        "workflow_url": run.workflow_url,
        "overall_status": run.overall_status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    stages = (
        db.query(PipelineStage)
        .filter(PipelineStage.pipeline_run_id == run.id)
        .order_by(PipelineStage.id.asc())
        .all()
    )
    stage_payloads = [stage_to_dict(stage) for stage in stages]

    quality_stage = next((stage for stage in stages if stage.stage_name == "quality_gate"), None)
    if quality_stage:
        payload["quality_summary"] = quality_stage.summary_json or {}
        payload["quality_artifacts"] = quality_stage.artifacts_json or {}

    if include_details:
        stage_ids = [stage.id for stage in stages]
        findings_by_stage: dict[int, list[dict[str, Any]]] = {stage_id: [] for stage_id in stage_ids}
        if stage_ids:
            stored_findings = (
                db.query(QualityFinding)
                .filter(QualityFinding.pipeline_stage_id.in_(stage_ids))
                .order_by(QualityFinding.id.asc())
                .all()
            )
            for finding in stored_findings:
                findings_by_stage.setdefault(finding.pipeline_stage_id, []).append(
                    {
                        "id": finding.id,
                        "scanner": finding.scanner,
                        "severity": finding.severity,
                        "rule_id": finding.rule_id,
                        "title": finding.title,
                        "message": finding.message,
                        "file_path": finding.file_path,
                        "line_number": finding.line_number,
                        "recommendation": finding.recommendation,
                        "created_at": finding.created_at.isoformat() if finding.created_at else None,
                    }
                )

        for stage_payload in stage_payloads:
            stage_payload["findings"] = findings_by_stage.get(stage_payload["id"], [])

    payload["stages"] = stage_payloads

    if include_details and quality_stage:
        findings = (
            db.query(QualityFinding)
            .filter(QualityFinding.pipeline_stage_id == quality_stage.id)
            .order_by(QualityFinding.id.asc())
            .all()
        )
        payload["quality_findings"] = [
            {
                "id": finding.id,
                "scanner": finding.scanner,
                "severity": finding.severity,
                "rule_id": finding.rule_id,
                "title": finding.title,
                "message": finding.message,
                "file_path": finding.file_path,
                "line_number": finding.line_number,
                "recommendation": finding.recommendation,
                "created_at": finding.created_at.isoformat() if finding.created_at else None,
            }
            for finding in findings
        ]

    return payload
