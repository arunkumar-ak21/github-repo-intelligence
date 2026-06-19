"""Sanitize inbound reports before storage, display, logs, or AI usage."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "access_key",
    "api_key",
    "authorization",
    "client_secret",
    "code_snippet",
    "credential",
    "credentials",
    "hashed_secret",
    "match",
    "password",
    "private_key",
    "secret",
    "secret_key",
    "token",
    "value",
}

SECRET_SCANNERS = {"custom-patterns", "detect-secrets", "gitleaks", "secrets", "trufflehog"}


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEYS)


def _is_secret_finding(payload: dict[str, Any]) -> bool:
    category = str(payload.get("category") or "").lower()
    scanner = str(payload.get("scanner") or payload.get("scanner_name") or "").lower()
    return category == "secrets" or scanner in SECRET_SCANNERS


def sanitize_payload(payload: Any) -> Any:
    """Recursively redact likely secret values from arbitrary JSON-like payloads."""
    if isinstance(payload, dict):
        secret_finding = _is_secret_finding(payload)
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if _is_sensitive_key(key):
                sanitized[key] = REDACTED
            elif secret_finding and key in {"raw", "raw_value", "finding", "line"}:
                sanitized[key] = REDACTED
            else:
                sanitized[key] = sanitize_payload(value)
        return sanitized

    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]

    return payload


def sanitize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Return the dashboard-safe finding shape."""
    safe = sanitize_payload(deepcopy(finding))
    return {
        "scanner": safe.get("scanner"),
        "severity": safe.get("severity"),
        "rule_id": safe.get("rule_id"),
        "title": safe.get("title"),
        "message": safe.get("message"),
        "file_path": safe.get("file_path"),
        "line_number": safe.get("line_number"),
        "recommendation": safe.get("recommendation") or safe.get("suggestion"),
    }
