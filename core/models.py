from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from datetime import datetime, timezone
from .database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    github_account_id = Column(Integer, index=True, nullable=True)
    github_account_login = Column(String, index=True, nullable=True)
    github_account_type = Column(String, nullable=True)
    plan = Column(String, nullable=False, default="starter")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_user_id = Column(Integer, unique=True, index=True, nullable=False)
    github_login = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = Column(DateTime, nullable=True)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership_identity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    role = Column(String, index=True, nullable=False, default="viewer")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class GitHubInstallation(Base):
    __tablename__ = "github_installations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    installation_id = Column(Integer, unique=True, index=True, nullable=False)
    account_id = Column(Integer, index=True, nullable=True)
    account_login = Column(String, index=True, nullable=True)
    account_type = Column(String, nullable=True)
    permissions_json = Column(JSON, nullable=True)
    repository_selection = Column(String, nullable=True)
    installed_at = Column(DateTime, nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    raw_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    repo = Column(String, index=True, nullable=False)
    analyzed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    language = Column(String, nullable=True)
    health_score = Column(Float, nullable=True)
    risk_level = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    cicd_json = Column(JSON, nullable=True)
    dependencies_json = Column(JSON, nullable=True)
    batch_id = Column(String, nullable=True)
    stars = Column(Integer, nullable=True)
    forks = Column(Integer, nullable=True)
    open_issues = Column(Integer, nullable=True)
    default_branch = Column(String, nullable=True)
    license_name = Column(String, nullable=True)
    topics = Column(JSON, nullable=True)
    cicd_platforms = Column(JSON, nullable=True)
    build_health = Column(String, nullable=True)
    total_dependencies = Column(Integer, nullable=True)
    vulnerable_count = Column(Integer, nullable=True)
    outdated_count = Column(Integer, nullable=True)
    analysis_duration_ms = Column(Integer, nullable=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "repo",
            "commit_sha",
            "workflow_run_id",
            name="uq_pipeline_run_identity",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    repository_id = Column(Integer, ForeignKey("monitored_repositories.id"), index=True, nullable=True)
    repo = Column(String, index=True, nullable=False)
    branch = Column(String, index=True, nullable=True)
    commit_sha = Column(String, index=True, nullable=False)
    pr_number = Column(Integer, nullable=True)
    workflow_run_id = Column(String, index=True, nullable=False)
    workflow_url = Column(Text, nullable=True)
    overall_status = Column(String, index=True, nullable=False, default="running")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    raw_json = Column(JSON, nullable=True)


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_run_id", "stage_name", name="uq_pipeline_stage_identity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), index=True, nullable=False)
    stage_name = Column(String, index=True, nullable=False)
    status = Column(String, index=True, nullable=False)
    blocking = Column(Boolean, default=False, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    summary_json = Column(JSON, nullable=True)
    artifacts_json = Column(JSON, nullable=True)
    raw_json = Column(JSON, nullable=True)


class QualityFinding(Base):
    __tablename__ = "quality_findings"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    pipeline_stage_id = Column(Integer, ForeignKey("pipeline_stages.id"), index=True, nullable=False)
    scanner = Column(String, index=True, nullable=True)
    severity = Column(String, index=True, nullable=True)
    rule_id = Column(String, index=True, nullable=True)
    title = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)
    line_number = Column(Integer, nullable=True)
    recommendation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class MonitoredRepository(Base):
    __tablename__ = "monitored_repositories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "full_name", name="uq_monitored_repo_tenant_full_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    installation_id = Column(Integer, ForeignKey("github_installations.id"), index=True, nullable=True)
    full_name = Column(String, index=True, nullable=False)
    owner = Column(String, index=True, nullable=False)
    repo = Column(String, index=True, nullable=False)
    default_branch = Column(String, nullable=True)
    setup_status = Column(String, index=True, nullable=False, default="pending")
    is_active = Column(Boolean, default=True, nullable=False)
    workflow_installed_at = Column(DateTime, nullable=True)
    secrets_configured_at = Column(DateTime, nullable=True)
    ruleset_configured_at = Column(DateTime, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RepositoryApiKey(Base):
    __tablename__ = "repository_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=False)
    repository_id = Column(Integer, ForeignKey("monitored_repositories.id"), index=True, nullable=False)
    key_prefix = Column(String, index=True, nullable=False)
    key_hash = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, index=True, nullable=False, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    rotated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    event_type = Column(String, index=True, nullable=False)
    target_type = Column(String, index=True, nullable=True)
    target_id = Column(String, index=True, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    metadata_json = Column(JSON, nullable=True)
