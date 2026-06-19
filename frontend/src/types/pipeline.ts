export type PipelineStatus =
  | "pending"
  | "running"
  | "passed"
  | "failed"
  | "blocked"
  | "error"
  | "skipped"
  | "needs_human"
  | "completed"
  | string;

export type SeveritySummary = {
  total_findings?: number;
  critical?: number;
  high?: number;
  medium?: number;
  low?: number;
  files_scanned?: number;
  duration_seconds?: number;
  [key: string]: unknown;
};

export type PipelineStage = {
  id?: number;
  tenant_id?: number;
  pipeline_run_id?: number;
  stage_name: string;
  status?: PipelineStatus | null;
  blocking?: boolean | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  summary?: SeveritySummary;
  artifacts?: Record<string, unknown>;
  findings?: PipelineStageFinding[];
};

export type PipelineStageFinding = {
  id?: number;
  scanner?: string | null;
  severity?: string | null;
  rule_id?: string | null;
  title?: string | null;
  message?: string | null;
  file_path?: string | null;
  line_number?: number | null;
  recommendation?: string | null;
  created_at?: string | null;
};

export type PipelineRun = {
  id: number;
  tenant_id?: number;
  repository_id?: number | null;
  repo: string;
  branch?: string | null;
  commit_sha?: string | null;
  pr_number?: number | null;
  workflow_run_id?: string | null;
  workflow_url?: string | null;
  overall_status?: PipelineStatus | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  stages?: PipelineStage[];
  quality_findings?: PipelineStageFinding[];
  quality_summary?: SeveritySummary;
  quality_artifacts?: Record<string, unknown>;
};

export type AuthStatus = {
  authenticated: boolean;
  require_login: boolean;
  app_name?: string;
  github_login_configured?: boolean;
  github_app_configured?: boolean;
  github_app_install_url?: string;
  user?: {
    github_login?: string;
    name?: string | null;
    avatar_url?: string | null;
  } | null;
  tenants?: Array<{
    id: number;
    name: string;
    slug: string;
    role?: string;
  }>;
  selected_tenant_id?: number | string | null;
};

export type AnalysisPayload = {
  repo?: string;
  analyzed_at?: string;
  analysis_duration_ms?: number;
  history_id?: number | null;
  cache_hit?: boolean;
  metadata?: Record<string, any>;
  cicd?: Record<string, any>;
  dependencies?: Record<string, any>;
  metadata_json?: Record<string, any>;
  cicd_json?: Record<string, any>;
  dependencies_json?: Record<string, any>;
  metadata_details?: Record<string, any>;
  [key: string]: any;
};

export type AnalysisHistoryItem = {
  id: number;
  repo: string;
  analyzed_at?: string;
  language?: string | null;
  health_score?: number | null;
  risk_level?: string | null;
  batch_id?: string | null;
  stars?: number | null;
  forks?: number | null;
  open_issues?: number | null;
  default_branch?: string | null;
  license_name?: string | null;
  topics?: string[];
  cicd_platforms?: string[];
  total_dependencies?: number | null;
  vulnerable_count?: number | null;
  outdated_count?: number | null;
  analysis_duration_ms?: number | null;
  metadata?: Record<string, any>;
  cicd?: Record<string, any>;
  dependencies?: Record<string, any>;
};

export type SetupRepository = {
  id: number;
  full_name: string;
  owner?: string;
  repo?: string;
  setup_status?: string;
  is_active?: boolean;
  default_branch?: string | null;
  installation_id?: number | null;
  workflow_installed_at?: string | null;
  secrets_configured_at?: string | null;
  ruleset_configured_at?: string | null;
  last_setup_error?: string | null;
  ignored_at?: string | null;
  deprovisioned_at?: string | null;
  setup_pr_number?: number | null;
  setup_pr_url?: string | null;
  setup_pr_branch?: string | null;
  cleanup_pr_number?: number | null;
  cleanup_pr_url?: string | null;
  cleanup_pr_branch?: string | null;
  last_sync_at?: string | null;
  last_verified_at?: string | null;
  last_deprovision_error?: string | null;
  provisioning_ready?: boolean;
  provisioning_blockers?: string[];
  api_key_prefix?: string | null;
  created_at?: string | null;
};
