"""Centralized application configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """Application-wide settings with local-dev defaults."""

    APP_NAME: str = os.getenv("APP_NAME", "Arya tech Repo Quality Platform")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    DEFAULT_TENANT_NAME: str = os.getenv("DEFAULT_TENANT_NAME", "Local Development")
    DEFAULT_TENANT_SLUG: str = os.getenv("DEFAULT_TENANT_SLUG", "local-dev")
    REQUIRE_LOGIN: bool = os.getenv("REQUIRE_LOGIN", "false").strip().lower() in {"1", "true", "yes", "on"}
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "local-dev-session-secret-change-me")
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "arya_quality_session")
    SESSION_MAX_AGE_SECONDS: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", "604800"))
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}

    GITHUB_APP_NAME: str = os.getenv("GITHUB_APP_NAME", "Arya tech Repo Quality Platform")
    GITHUB_APP_SLUG: str = os.getenv("GITHUB_APP_SLUG", "").strip()
    GITHUB_APP_INSTALL_URL: str = os.getenv("GITHUB_APP_INSTALL_URL", "").strip()
    GITHUB_APP_ID: str = os.getenv("GITHUB_APP_ID", "").strip()
    GITHUB_APP_CLIENT_ID: str = os.getenv("GITHUB_APP_CLIENT_ID", "").strip()
    GITHUB_APP_CLIENT_SECRET: str = os.getenv("GITHUB_APP_CLIENT_SECRET", "").strip()
    GITHUB_APP_PRIVATE_KEY: str = os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip()
    GITHUB_APP_PRIVATE_KEY_PATH: str = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
    GITHUB_APP_WEBHOOK_SECRET: str = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "").strip()
    GITHUB_API_VERSION: str = os.getenv("GITHUB_API_VERSION", "2022-11-28")

    QUALITY_CALLER_WORKFLOW_PATH: str = os.getenv(
        "QUALITY_CALLER_WORKFLOW_PATH",
        ".github/workflows/company-quality-pipeline.yml",
    )
    QUALITY_REUSABLE_WORKFLOW_REF: str = os.getenv(
        "QUALITY_REUSABLE_WORKFLOW_REF",
        "company/repo-quality-platform/.github/workflows/reusable-quality-gate.yml@main",
    )
    QUALITY_WORKFLOW_MODE: str = os.getenv("QUALITY_WORKFLOW_MODE", "standalone").strip().lower()
    PROVISIONING_DRY_RUN: bool = os.getenv("PROVISIONING_DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}
    AUTO_SYNC_REPOS_ON_INSTALL: bool = os.getenv(
        "AUTO_SYNC_REPOS_ON_INSTALL", "true"
    ).strip().lower() in {"1", "true", "yes", "on"}
    AUTO_PROVISION_ON_INSTALL: bool = os.getenv(
        "AUTO_PROVISION_ON_INSTALL", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    AUTO_PROVISION_ON_SYNC: bool = os.getenv(
        "AUTO_PROVISION_ON_SYNC", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    AUTO_REPROVISION_ACTIVE_REPOS: bool = os.getenv(
        "AUTO_REPROVISION_ACTIVE_REPOS", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING: bool = os.getenv(
        "ALLOW_LOCAL_DASHBOARD_URL_FOR_PROVISIONING", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}

    _raw_github_token = os.getenv("GITHUB_TOKEN", "").strip()
    GITHUB_TOKEN: str = "" if _raw_github_token in {"", "your_github_token_here"} else _raw_github_token

    DATA_DIR: Path = PROJECT_ROOT / "data"
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "900"))

    REPORTS_DIR: Path = DATA_DIR / "reports"

    DASHBOARD_API_KEY: str = os.getenv("DASHBOARD_API_KEY", "").strip()
    ALLOW_UNREGISTERED_REPOS: bool = os.getenv(
        "ALLOW_UNREGISTERED_REPOS", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    MAX_REPORT_PAYLOAD_BYTES: int = int(os.getenv("MAX_REPORT_PAYLOAD_BYTES", "5242880"))
    MAX_FINDINGS_PER_REPORT: int = int(os.getenv("MAX_FINDINGS_PER_REPORT", "500"))
    REPORT_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("REPORT_RATE_LIMIT_PER_MINUTE", "120"))
    ENABLE_LOCAL_QUALITY_SCAN: bool = os.getenv(
        "ENABLE_LOCAL_QUALITY_SCAN", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if origin.strip()
    ]

    def __init__(self) -> None:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
