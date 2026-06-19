"""
CI/CD Pipeline Detector Module
Scans repositories to find CI/CD pipeline definition files across 9 major platforms.

Supported Platforms:
  • GitHub Actions    • GitLab CI       • Jenkins
  • Azure DevOps      • CircleCI        • Travis CI
  • Drone CI          • Bitbucket       • TeamCity
"""

import os
from pathlib import Path

# ── Platform Registry ─────────────────────────────────────────────────────────
# Each entry defines how to locate pipeline files for that CI/CD platform.

PIPELINE_PATTERNS = {
    "GitHub Actions": {
        "paths": [".github/workflows"],
        "extensions": [".yml", ".yaml"],
        "type": "directory",
        "docs_url": "https://docs.github.com/en/actions",
        "icon": "⚙️",
        "color": "#238636",
    },
    "GitLab CI": {
        "paths": [".gitlab-ci.yml"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://docs.gitlab.com/ee/ci/",
        "icon": "🦊",
        "color": "#fc6d26",
    },
    "Jenkins": {
        "paths": ["Jenkinsfile", "Jenkinsfile.groovy"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://www.jenkins.io/doc/book/pipeline/",
        "icon": "🔧",
        "color": "#335061",
    },
    "Azure DevOps": {
        "paths": ["azure-pipelines.yml", "azure-pipelines.yaml"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://learn.microsoft.com/en-us/azure/devops/pipelines/",
        "icon": "☁️",
        "color": "#0078d4",
    },
    "CircleCI": {
        "paths": [".circleci/config.yml", ".circleci/config.yaml"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://circleci.com/docs/",
        "icon": "⭕",
        "color": "#343434",
    },
    "Travis CI": {
        "paths": [".travis.yml"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://docs.travis-ci.com/",
        "icon": "🏗️",
        "color": "#3eaaaf",
    },
    "Drone CI": {
        "paths": [".drone.yml", ".drone.yaml"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://docs.drone.io/",
        "icon": "🚁",
        "color": "#1a6496",
    },
    "Bitbucket Pipelines": {
        "paths": ["bitbucket-pipelines.yml"],
        "extensions": [],
        "type": "file",
        "docs_url": "https://support.atlassian.com/bitbucket-cloud/docs/get-started-with-bitbucket-pipelines/",
        "icon": "🪣",
        "color": "#0052cc",
    },
    "TeamCity": {
        "paths": [".teamcity"],
        "extensions": [".kts", ".xml"],
        "type": "directory",
        "docs_url": "https://www.jetbrains.com/help/teamcity/",
        "icon": "🏙️",
        "color": "#21d789",
    },
}

# Reverse lookup: file path pattern → platform name (used by github_agent.py)
PIPELINE_FILE_MAP = {
    ".github/workflows":        "GitHub Actions",   # prefix match
    ".gitlab-ci.yml":           "GitLab CI",
    "Jenkinsfile":              "Jenkins",
    "Jenkinsfile.groovy":       "Jenkins",
    "azure-pipelines.yml":      "Azure DevOps",
    "azure-pipelines.yaml":     "Azure DevOps",
    ".circleci/config.yml":     "CircleCI",
    ".circleci/config.yaml":    "CircleCI",
    ".travis.yml":              "Travis CI",
    ".drone.yml":               "Drone CI",
    ".drone.yaml":              "Drone CI",
    "bitbucket-pipelines.yml":  "Bitbucket Pipelines",
}


# ── Core Detection ────────────────────────────────────────────────────────────

def detect_pipelines(repo_path: str) -> dict:
    """
    Scan a repository path and detect all CI/CD pipeline files.

    Args:
        repo_path: Path to the repository root.

    Returns:
        dict: {
            platform_name: {
                "files": [list of absolute file paths],
                "docs_url": str,
                "icon": str,
                "color": str,
            }
        }

    Raises:
        FileNotFoundError: If repo_path does not exist.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise FileNotFoundError(f"Repository path not found: {repo}")

    results = {}

    for platform, config in PIPELINE_PATTERNS.items():
        found_files = []

        for pattern_path in config["paths"]:
            full_path = repo / pattern_path

            if config["type"] == "directory":
                if full_path.is_dir():
                    for ext in config["extensions"]:
                        found_files.extend(
                            str(f) for f in sorted(full_path.glob(f"*{ext}"))
                        )
            else:
                if full_path.is_file():
                    found_files.append(str(full_path))

        if found_files:
            results[platform] = {
                "files":    found_files,
                "docs_url": config["docs_url"],
                "icon":     config["icon"],
                "color":    config["color"],
            }

    return results


def get_file_platform(file_path: str) -> str | None:
    """
    Determine which CI/CD platform owns a given file path.
    Useful for single-file lookups without a full repo scan.

    Args:
        file_path: Relative or absolute file path string.

    Returns:
        Platform name string, or None if unrecognised.
    """
    p = file_path.replace("\\", "/")

    # Directory prefix match (GitHub Actions workflows)
    if p.startswith(".github/workflows/") and (p.endswith(".yml") or p.endswith(".yaml")):
        return "GitHub Actions"

    # TeamCity directory
    if p.startswith(".teamcity/"):
        return "TeamCity"

    # Exact / basename matches
    basename = p.split("/")[-1]
    for key, platform in PIPELINE_FILE_MAP.items():
        if p == key or basename == key.split("/")[-1]:
            return platform

    return None


def get_platform_summary(results: dict) -> list[dict]:
    """
    Generate a flat summary list from detect_pipelines() output.

    Returns:
        List of dicts with keys: platform, file_count, files, docs_url, icon, color.
    """
    summary = []
    for platform, data in results.items():
        summary.append({
            "platform":   platform,
            "file_count": len(data["files"]),
            "files":      [os.path.basename(f) for f in data["files"]],
            "docs_url":   data["docs_url"],
            "icon":       data.get("icon", "📦"),
            "color":      data.get("color", "#334155"),
        })
    return summary


def get_platform_config(platform: str) -> dict:
    """Return the full config dict for a platform, or empty dict."""
    return PIPELINE_PATTERNS.get(platform, {})
