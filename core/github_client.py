"""
Unified GitHub API Client
=========================
Merges the best parts of all three interns' GitHub API code:

- Arun's retry/backoff logic and rate-limit handling
- Satyam's repo-tree and raw-content fetching
- Mohit's contributor/commit extraction (replaces PyGithub with REST API)

All modules share this single client instance so that:
  1. Only one GitHub token is used (shared rate limit)
  2. Responses are cached in-memory (no duplicate API calls)
  3. Rate limit is tracked centrally
"""

import time
import base64
import logging
import hashlib
from typing import Optional
from datetime import datetime, timezone
from collections import OrderedDict

import requests

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
MAX_RETRIES = 3
BACKOFF_FACTOR = 2  # seconds — doubles on each retry


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class GitHubAPIError(Exception):
    """Raised when a GitHub API call fails after all retries."""


class RateLimitError(GitHubAPIError):
    """Raised when rate limit is exhausted and cannot be waited out."""


# ---------------------------------------------------------------------------
# Simple LRU Cache (thread-safe enough for our use case)
# ---------------------------------------------------------------------------
class _LRUCache:
    """Minimal LRU cache with TTL (time-to-live) in seconds."""

    def __init__(self, maxsize: int = 256, ttl: int = 300):
        self._cache: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str):
        if key in self._cache:
            ts, value = self._cache[key]
            if time.time() - ts < self._ttl:
                self._cache.move_to_end(key)
                return value
            else:
                del self._cache[key]
        return None

    def put(self, key: str, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


# ---------------------------------------------------------------------------
# Unified GitHub Client
# ---------------------------------------------------------------------------
class GitHubClient:
    """
    Single shared client for all GitHub API interactions.

    Parameters
    ----------
    token : str or None
        GitHub Personal Access Token. If provided, rate limit
        increases from 60 → 5,000 requests/hour.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitHubRepoIntelligence/1.0",
        })
        self.token = token
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
            logger.info("GitHub client initialized with auth token.")
        else:
            logger.warning(
                "No GitHub token — rate limit is 60 req/hr. "
                "Set GITHUB_TOKEN env var for 5,000 req/hr."
            )

        # In-memory response cache (5 min TTL)
        self._cache = _LRUCache(maxsize=512, ttl=300)

    # ------------------------------------------------------------------
    # Core request with retry + rate-limit handling (from Arun's client)
    # ------------------------------------------------------------------
    def _request(
        self, method: str, url: str, use_cache: bool = True, **kwargs
    ) -> requests.Response:
        """
        Execute an HTTP request with automatic retry on rate-limit (403/429)
        and transient server errors (5xx).
        """
        cache_key = None
        if method.upper() == "GET" and use_cache:
            cache_key = hashlib.md5(url.encode()).hexdigest()
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)
            except requests.RequestException as exc:
                logger.error("Network error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt == MAX_RETRIES:
                    raise GitHubAPIError(
                        f"Network error after {MAX_RETRIES} attempts: {exc}"
                    ) from exc
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue

            # Rate limit handling (403 + 429)
            if resp.status_code in (403, 429) and (
                "rate limit" in resp.text.lower() or resp.status_code == 429
            ):
                reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
                wait = max(reset_ts - int(time.time()), 1)
                if wait > 300:
                    raise RateLimitError(
                        f"Rate limit exceeded. Resets in {wait}s (~{wait // 60} min). "
                        "Provide a GITHUB_TOKEN to increase your quota."
                    )
                logger.warning(
                    "Rate limit hit (HTTP %d) — sleeping %ds until reset…",
                    resp.status_code, wait,
                )
                time.sleep(wait + 1)
                continue

            # 404 — valid "not found"
            if resp.status_code == 404:
                return resp

            # Server errors — retry
            if resp.status_code >= 500:
                logger.warning(
                    "Server error %d (attempt %d/%d)",
                    resp.status_code, attempt, MAX_RETRIES,
                )
                if attempt == MAX_RETRIES:
                    raise GitHubAPIError(
                        f"GitHub returned {resp.status_code} after {MAX_RETRIES} retries."
                    )
                time.sleep(BACKOFF_FACTOR ** attempt)
                continue

            # Other client errors
            if resp.status_code >= 400:
                raise GitHubAPIError(
                    f"GitHub API error {resp.status_code}: "
                    f"{resp.json().get('message', resp.text)}"
                )

            # Success — cache it
            if cache_key is not None:
                self._cache.put(cache_key, resp)
            return resp

        raise GitHubAPIError("Request failed after all retries.")

    # ------------------------------------------------------------------
    # Rate Limit
    # ------------------------------------------------------------------
    def get_rate_limit(self) -> dict:
        """Return current GitHub API rate-limit status."""
        resp = self._request("GET", f"{GITHUB_API}/rate_limit", use_cache=False)
        data = resp.json()
        core = data.get("resources", {}).get("core", {})
        return {
            "limit": core.get("limit", 0),
            "remaining": core.get("remaining", 0),
            "reset_epoch": core.get("reset", 0),
            "reset_utc": time.strftime(
                "%Y-%m-%d %H:%M:%S UTC", time.gmtime(core.get("reset", 0))
            ),
        }

    # ------------------------------------------------------------------
    # Repository Metadata (used by all 3 modules)
    # ------------------------------------------------------------------
    def get_repo_info(self, repo: str) -> Optional[dict]:
        """Fetch repository metadata. Returns None if not found."""
        resp = self._request("GET", f"{GITHUB_API}/repos/{repo}")
        if resp.status_code == 404:
            return None
        return resp.json()

    # ------------------------------------------------------------------
    # Pagination Helpers
    # ------------------------------------------------------------------
    def get_count_from_link_header(self, link_header: str, fallback_count: int = 0) -> int:
        if not link_header:
            return fallback_count

        import re
        match = re.search(r'[?&]page=(\d+)>; rel="last"', link_header)

        if match:
            return int(match.group(1))

        return fallback_count

    def get_paginated_total_count(self, endpoint: str) -> int:
        resp = self._request("GET", f"{GITHUB_API}{endpoint}?per_page=1", use_cache=True)

        if resp.status_code == 404:
            return 0

        data = resp.json()
        fallback_count = len(data) if isinstance(data, list) else 0

        return self.get_count_from_link_header(
            resp.headers.get("Link", ""),
            fallback_count
        )

    # ------------------------------------------------------------------
    # File Contents (used by Arun + Satyam)
    # ------------------------------------------------------------------
    def get_repo_root_contents(self, repo: str) -> Optional[list]:
        """List files at the repository root."""
        resp = self._request("GET", f"{GITHUB_API}/repos/{repo}/contents/")
        if resp.status_code == 404:
            return None
        return resp.json()

    def get_file_content(self, repo: str, path: str) -> Optional[str]:
        """Download and decode UTF-8 text of a file."""
        url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
        resp = self._request("GET", url)
        if resp.status_code == 404:
            return None

        data = resp.json()
        if isinstance(data, list):
            return None

        content_b64 = data.get("content")
        if content_b64:
            try:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
            except Exception:
                logger.warning("Could not decode base64 for %s/%s", repo, path)

        download_url = data.get("download_url")
        if download_url:
            raw = self.session.get(download_url, timeout=30)
            if raw.status_code == 200:
                return raw.text

        return None

    def get_directory_contents(self, repo: str, path: str) -> Optional[list]:
        """List files in a subdirectory."""
        url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
        resp = self._request("GET", url)
        if resp.status_code == 404:
            return None
        data = resp.json()
        return data if isinstance(data, list) else None

    # ------------------------------------------------------------------
    # Repository Tree (used by Satyam + Mohit)
    # ------------------------------------------------------------------
    def get_repo_tree(self, repo: str, branch: str = "main") -> list[str]:
        """Fetch full recursive file tree. Returns list of file paths."""
        url = f"{GITHUB_API}/repos/{repo}/git/trees/{branch}?recursive=1"
        resp = self._request("GET", url)
        if resp.status_code in (404, 409):
            return []
        data = resp.json()
        if data.get("truncated"):
            logger.warning("Tree truncated (>100k files) for %s", repo)
        return [
            item["path"]
            for item in data.get("tree", [])
            if item.get("type") == "blob"
        ]

    def get_raw_content(
        self, owner: str, repo: str, branch: str, path: str
    ) -> str:
        """Download raw file content from raw.githubusercontent.com."""
        url = f"{RAW_BASE}/{owner}/{repo}/{branch}/{path}"
        resp = self._request("GET", url)
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------------
    # Workflow / Actions (used by Satyam)
    # ------------------------------------------------------------------
    def get_latest_workflow_run(self, repo: str) -> dict:
        """Fetch the latest GitHub Actions workflow run status."""
        try:
            url = f"{GITHUB_API}/repos/{repo}/actions/runs?per_page=1"
            resp = self._request("GET", url, use_cache=False)
            if resp.status_code != 200:
                return {}
            runs = resp.json().get("workflow_runs", [])
            if not runs:
                return {}
            run = runs[0]
            return {
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "name": run.get("name"),
                "run_number": run.get("run_number"),
                "html_url": run.get("html_url"),
                "created_at": run.get("created_at"),
            }
        except Exception:
            return {}

    def get_workflow_runs(self, repo: str, per_page: int = 10) -> list[dict]:
        """Fetch recent GitHub Actions workflow runs.

        Returns a list of run dicts with id, name, status, conclusion,
        timestamps, and html_url.
        """
        try:
            url = f"{GITHUB_API}/repos/{repo}/actions/runs?per_page={per_page}"
            resp = self._request("GET", url, use_cache=False)
            if resp.status_code != 200:
                return []
            runs = resp.json().get("workflow_runs", [])
            return [
                {
                    "id": run.get("id"),
                    "name": run.get("name"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "run_number": run.get("run_number"),
                    "html_url": run.get("html_url"),
                    "created_at": run.get("created_at"),
                    "updated_at": run.get("updated_at"),
                    "head_branch": run.get("head_branch"),
                    "event": run.get("event"),
                }
                for run in runs
            ]
        except Exception as exc:
            logger.warning("Failed to fetch workflow runs for %s: %s", repo, exc)
            return []

    def get_workflow_run_artifacts(self, repo: str, run_id: int) -> list[dict]:
        """Fetch artifacts produced by a specific workflow run.

        Returns a list of artifact dicts with name, size, and expiry info.
        """
        try:
            url = f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/artifacts"
            resp = self._request("GET", url, use_cache=True)
            if resp.status_code != 200:
                return []
            artifacts = resp.json().get("artifacts", [])
            return [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "size_in_bytes": a.get("size_in_bytes", 0),
                    "expired": a.get("expired", False),
                    "created_at": a.get("created_at"),
                    "expires_at": a.get("expires_at"),
                }
                for a in artifacts
            ]
        except Exception as exc:
            logger.warning(
                "Failed to fetch artifacts for %s run %s: %s", repo, run_id, exc
            )
            return []

    # ------------------------------------------------------------------
    # Dependabot Alerts (used by Arun)
    # ------------------------------------------------------------------
    def get_dependabot_alerts(self, repo: str) -> list:
        """Fetch Dependabot alerts. Returns [] if access denied."""
        url = f"{GITHUB_API}/repos/{repo}/dependabot/alerts"
        try:
            resp = self._request("GET", url)
            if resp.status_code == 200:
                return resp.json()
            return []
        except GitHubAPIError:
            logger.debug("Dependabot alerts unavailable for %s", repo)
            return []

    # ------------------------------------------------------------------
    # Commits, Contributors, File Tree (used by Mohit)
    # ------------------------------------------------------------------
    def get_commits(self, repo: str, per_page: int = 100) -> list[dict]:
        """Fetch commit history (up to per_page commits)."""
        url = f"{GITHUB_API}/repos/{repo}/commits?per_page={per_page}"
        resp = self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_contributors(self, repo: str, per_page: int = 100) -> list[dict]:
        """Fetch contributors list."""
        url = f"{GITHUB_API}/repos/{repo}/contributors?per_page={per_page}"
        resp = self._request("GET", url)
        if resp.status_code == 200:
            return resp.json()
        return []

    def get_readme(self, repo: str) -> Optional[str]:
        """Fetch and decode the README file."""
        url = f"{GITHUB_API}/repos/{repo}/readme"
        resp = self._request("GET", url)
        if resp.status_code == 404:
            return None
        data = resp.json()
        content_b64 = data.get("content")
        if content_b64:
            try:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
            except Exception:
                pass
        return None

    def get_topics(self, repo: str) -> list[str]:
        """Fetch repository topics."""
        url = f"{GITHUB_API}/repos/{repo}/topics"
        headers = {"Accept": "application/vnd.github.mercy-preview+json"}
        try:
            resp = self._request("GET", url, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("names", [])
        except Exception:
            pass
        return []


# ---------------------------------------------------------------------------
# Singleton instance — shared across all modules
# ---------------------------------------------------------------------------
_client: Optional[GitHubClient] = None


def get_github_client() -> GitHubClient:
    """Return the shared GitHubClient singleton."""
    global _client
    if _client is None:
        _client = GitHubClient(token=settings.GITHUB_TOKEN or None)
    return _client
