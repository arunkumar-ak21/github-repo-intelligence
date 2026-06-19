"""
Build Artifact Verifier
=======================
Verifies whether GitHub Actions workflows successfully produce build
artifacts. A workflow that is *expected* to compile/build source code
should produce artifacts. If it doesn't, that signals a build failure
or misconfiguration.

Flow
----
1. Fetch the last N completed workflow runs via the GitHub Actions API.
2. For each run, check whether it produced any artifacts.
3. Classify each run:
   - ``success``  — conclusion is "success" AND artifacts were produced
   - ``success_no_artifact`` — conclusion is "success" but no artifacts
   - ``failed``   — conclusion is "failure" / "cancelled" / "timed_out"
   - ``in_progress`` — run is still queued or in progress (skipped)
4. Compute an overall **build health** status and artifact-producing rate.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.github_client import get_github_client

logger = logging.getLogger(__name__)

# Number of recent completed runs to inspect
DEFAULT_RUNS_TO_CHECK = 5

# Conclusions that count as "completed" (skip queued / in_progress)
_COMPLETED_CONCLUSIONS = {"success", "failure", "cancelled", "timed_out", "action_required", "skipped"}


def verify_build_artifacts(
    owner: str,
    repo: str,
    runs_to_check: int = DEFAULT_RUNS_TO_CHECK,
    progress_callback=None,
) -> dict:
    """Run build-artifact verification for a GitHub repository.

    Parameters
    ----------
    owner : str
        Repository owner.
    repo : str
        Repository name.
    runs_to_check : int
        How many recent *completed* runs to inspect (default 5).
    progress_callback : callable or None
        Optional ``(event, message)`` callback for live progress.

    Returns
    -------
    dict
        Structured build health report.
    """
    _cb = progress_callback if callable(progress_callback) else (lambda e, m: None)
    client = get_github_client()
    full_name = f"{owner}/{repo}"

    result: dict = {
        "build_health": "no_workflows",
        "total_runs_checked": 0,
        "successful_builds": 0,
        "failed_builds": 0,
        "no_artifact_builds": 0,
        "artifact_producing_rate": 0.0,
        "latest_run": None,
        "runs": [],
        "errors": [],
    }

    # -- 1. Fetch recent workflow runs ----------------------------------------
    _cb("build_verify_start", f"Fetching workflow runs for {full_name}...")

    if not client.token:
        result["errors"].append(
            "GitHub token not configured — workflow run data may be limited."
        )

    # Fetch more than needed so we can filter to completed runs
    raw_runs = client.get_workflow_runs(full_name, per_page=runs_to_check * 2)

    if not raw_runs:
        _cb("build_verify_done", "No GitHub Actions workflow runs found")
        result["build_health"] = "no_workflows"
        return result

    # Filter to completed runs only
    completed_runs = [
        r for r in raw_runs
        if r.get("status") == "completed"
        and r.get("conclusion") in _COMPLETED_CONCLUSIONS
    ][:runs_to_check]

    if not completed_runs:
        _cb("build_verify_done", "No completed workflow runs found")
        result["build_health"] = "no_workflows"
        return result

    # -- 2. Check each run for artifacts --------------------------------------
    run_details: list[dict] = []

    for i, run in enumerate(completed_runs, 1):
        run_id = run["id"]
        run_name = run.get("name", "Unnamed")
        conclusion = run.get("conclusion", "unknown")

        _cb(
            "build_verify_checking",
            f"Checking run #{run.get('run_number', '?')} — {run_name} ({i}/{len(completed_runs)})",
        )

        artifacts = client.get_workflow_run_artifacts(full_name, run_id)
        has_artifacts = len(artifacts) > 0
        total_artifact_size = sum(a.get("size_in_bytes", 0) for a in artifacts)

        # Classify
        if conclusion == "success" and has_artifacts:
            classification = "success"
        elif conclusion == "success" and not has_artifacts:
            classification = "success_no_artifact"
        else:
            classification = "failed"

        detail = {
            "run_id": run_id,
            "run_number": run.get("run_number"),
            "name": run_name,
            "conclusion": conclusion,
            "classification": classification,
            "has_artifacts": has_artifacts,
            "artifact_count": len(artifacts),
            "total_artifact_size_bytes": total_artifact_size,
            "artifacts": artifacts,
            "html_url": run.get("html_url"),
            "created_at": run.get("created_at"),
            "event": run.get("event"),
            "head_branch": run.get("head_branch"),
        }
        run_details.append(detail)

    # -- 3. Compute aggregate metrics -----------------------------------------
    result["runs"] = run_details
    result["total_runs_checked"] = len(run_details)
    result["latest_run"] = run_details[0] if run_details else None

    result["successful_builds"] = sum(
        1 for r in run_details if r["classification"] == "success"
    )
    result["failed_builds"] = sum(
        1 for r in run_details if r["classification"] == "failed"
    )
    result["no_artifact_builds"] = sum(
        1 for r in run_details if r["classification"] == "success_no_artifact"
    )

    total = result["total_runs_checked"]
    if total > 0:
        result["artifact_producing_rate"] = round(
            (result["successful_builds"] / total) * 100, 1
        )

    # -- 4. Determine overall build health ------------------------------------
    rate = result["artifact_producing_rate"]
    failed = result["failed_builds"]

    if total == 0:
        result["build_health"] = "no_workflows"
    elif rate >= 80 and failed == 0:
        result["build_health"] = "healthy"
    elif rate >= 50 or (failed <= 1 and total >= 3):
        result["build_health"] = "degraded"
    else:
        result["build_health"] = "failing"

    # -- 5. Generate error messages for flagged issues ------------------------
    if result["no_artifact_builds"] > 0:
        result["errors"].append(
            f"{result['no_artifact_builds']} workflow run(s) succeeded but produced "
            f"no build artifacts — this may indicate a missing upload-artifact step "
            f"or a build configuration issue."
        )

    if result["failed_builds"] > 0:
        result["errors"].append(
            f"{result['failed_builds']} workflow run(s) failed. Check the GitHub "
            f"Actions logs for compilation or test errors."
        )

    health_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "failing": "❌",
        "no_workflows": "—",
    }
    emoji = health_emoji.get(result["build_health"], "❓")
    _cb(
        "build_verify_done",
        f"Build verification complete — {emoji} {result['build_health'].upper()} "
        f"({result['successful_builds']}/{total} runs produced artifacts)",
    )

    return result
