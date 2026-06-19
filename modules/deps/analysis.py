"""
Dependency Analysis Engine
==========================
Adapted from Arun's cli.py — same analysis pipeline, but uses the
shared GitHubClient instead of the standalone one.
"""

import logging
from datetime import datetime, timezone

from core.github_client import get_github_client, GitHubAPIError, RateLimitError
from .detector import EcosystemDetector
from .parsers import PARSER_REGISTRY
from .scorer import HealthScorer
from .package_apis import PackageAPIClient

logger = logging.getLogger(__name__)


def analyze_repo(repo: str, progress_callback=None) -> dict:
    """
    Run the full dependency analysis pipeline for a single repository.

    Parameters
    ----------
    repo : str
        Full repository name (e.g. "django/django").
    progress_callback : callable or None
        If provided, called with (step: str, detail: str) at each stage.

    Returns
    -------
    dict with analysis results.
    """
    client = get_github_client()

    def _progress(step: str, detail: str = ""):
        if progress_callback:
            progress_callback(step, detail)

    result = {
        "repository": repo,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "repo_info": {},
        "ecosystems": {},
        "dependencies": [],
        "health": {},
        "dependabot_alerts": [],
        "errors": [],
    }

    # Step 1: Repo metadata
    _progress("deps_fetching_metadata", f"Fetching repository info for {repo}...")
    repo_info = client.get_repo_info(repo)
    if repo_info is None:
        msg = f"Repository '{repo}' not found on GitHub."
        result["errors"].append(msg)
        return result

    result["repo_info"] = {
        "name": repo_info.get("full_name", repo),
        "description": repo_info.get("description", ""),
        "language": repo_info.get("language", ""),
        "stargazers_count": repo_info.get("stargazers_count", 0),
        "forks_count": repo_info.get("forks_count", 0),
        "open_issues_count": repo_info.get("open_issues_count", 0),
        "default_branch": repo_info.get("default_branch", "main"),
        "license": (repo_info.get("license") or {}).get("spdx_id", "N/A"),
        "archived": repo_info.get("archived", False),
        "pushed_at": repo_info.get("pushed_at"),
    }

    # Step 2: List root contents
    _progress("deps_scanning_files", "Scanning repository root directory...")
    root_files = client.get_repo_root_contents(repo)
    if root_files is None:
        msg = "Could not list repository root contents."
        result["errors"].append(msg)
        return result

    # Step 3: Detect ecosystems
    _progress("deps_detecting_ecosystems", "Detecting programming ecosystems...")
    detector = EcosystemDetector()
    ecosystems = detector.detect(root_files)
    result["ecosystems"] = ecosystems

    if not ecosystems:
        msg = "No supported dependency manifests found in the repo root."
        result["errors"].append(msg)

    # Step 4: Fetch and parse manifests
    all_deps_dict = {}
    any_lock = False

    for eco_name, eco_info in ecosystems.items():
        parser_cls = PARSER_REGISTRY.get(eco_name)
        if not parser_cls:
            logger.warning("No parser for ecosystem '%s'", eco_name)
            continue
        parser = parser_cls()

        if eco_info.get("has_lock_file"):
            any_lock = True

        files_to_parse = eco_info.get("manifest_files", []) + eco_info.get("lock_files", [])
        for manifest in files_to_parse:
            _progress("deps_parsing", f"Parsing {manifest}...")
            content = client.get_file_content(repo, manifest)
            if content is None:
                msg = f"Could not fetch {manifest}"
                result["errors"].append(msg)
                continue
            try:
                deps = parser.parse(content, manifest)
                for d in deps:
                    if d.name in all_deps_dict:
                        if not all_deps_dict[d.name].is_transitive:
                            d.is_transitive = False
                    all_deps_dict[d.name] = d
            except Exception as exc:
                msg = f"Parser error in {manifest}: {exc}"
                result["errors"].append(msg)
                logger.exception("Parser error for %s/%s", repo, manifest)

    all_deps = list(all_deps_dict.values())

    # Step 4.5: External API lookups
    _progress("deps_external_lookups", "Fetching latest versions and licenses...")
    api_client = PackageAPIClient()
    api_client.fetch_dependency_metadata(all_deps, ecosystems)

    _progress("deps_vulnerability_scan", "Fetching Dependabot alerts...")
    alerts = client.get_dependabot_alerts(repo)
    result["dependabot_alerts"] = alerts

    result["dependencies"] = [d.to_dict() for d in all_deps]

    # Step 5: Health score
    _progress("deps_computing_score", "Computing health score...")
    scorer = HealthScorer()
    health = scorer.score(
        all_deps,
        has_lock_file=any_lock,
        ecosystems_detected=len(ecosystems),
        dependabot_alerts=alerts,
        repo_license=result["repo_info"].get("license", "N/A"),
        pushed_at=result["repo_info"].get("pushed_at"),
        stargazers_count=result["repo_info"].get("stargazers_count", 0),
        is_archived=result["repo_info"].get("archived", False),
    )
    result["health"] = health

    _progress(
        "deps_complete",
        f"Analysis complete — score {health['score']}/100 [{health['risk_level']}]"
    )
    return result
