"""Optional local/demo adapter for running the real Code-Quality package."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import settings
from modules.security.sanitizer import sanitize_payload


def _load_cqpipeline():
    try:
        from cqpipeline.core.constants import ScanMode
        from cqpipeline.core.orchestrator import run_pipeline_sync
        from cqpipeline.reporters.html_reporter import HTMLReporter
        from cqpipeline.reporters.json_reporter import JSONReporter
    except ImportError as exc:
        raise RuntimeError(
            "Code-Quality package is not installed. For local prototype use: "
            "pip install -r requirements-quality-local.txt"
        ) from exc

    return ScanMode, run_pipeline_sync, JSONReporter, HTMLReporter


def run_local_quality_scan(project_root: Path) -> dict[str, Any]:
    """Run the standalone Code-Quality pipeline against a local path."""
    ScanMode, run_pipeline_sync, JSONReporter, HTMLReporter = _load_cqpipeline()

    root = project_root.resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist or is not a directory: {root}")

    report = run_pipeline_sync(project_root=root, scan_mode=ScanMode.ALL)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = settings.REPORTS_DIR / "quality-local" / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "quality-report.json"
    html_path = report_dir / "quality-report.html"

    JSONReporter().generate(report, output_path=json_path)
    HTMLReporter().generate(report, output_path=html_path)

    raw_report = sanitize_payload(report.model_dump(mode="json"))
    return {
        "mode": "local_demo",
        "project_root": str(root),
        "verdict": report.verdict.value,
        "summary": {
            "total_findings": report.total_findings,
            "critical": report.critical_count,
            "high": report.high_count,
            "medium": report.medium_count,
            "low": report.low_count,
            "files_scanned": report.files_scanned,
            "duration_seconds": report.duration_seconds,
        },
        "blocking_reasons": report.blocking_reasons,
        "artifacts": {
            "json_report": str(json_path),
            "html_report": str(html_path),
        },
        "raw_report": raw_report,
    }
