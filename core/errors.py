"""Application-specific error types for repository intelligence workflows."""

from __future__ import annotations

from typing import Any


class RepoHubError(Exception):
    """Base error with an HTTP status and stable machine-readable code."""

    status_code = 500
    code = "repohub_error"

    def __init__(self, message: str = "Repository intelligence error", **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": self.message,
            "code": self.code,
        }
        if self.context:
            payload["context"] = self.context
        return payload


class RepoNotFoundError(RepoHubError):
    status_code = 404
    code = "repo_not_found"


class RateLimitError(RepoHubError):
    status_code = 429
    code = "rate_limit_exceeded"


class PrivateRepoError(RepoHubError):
    status_code = 403
    code = "private_repo"


class AnalysisTimeoutError(RepoHubError):
    status_code = 504
    code = "analysis_timeout"
