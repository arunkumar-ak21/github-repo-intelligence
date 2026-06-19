import { apiGet } from "@/lib/api";
import type { AuthStatus, PipelineRun, PipelineStage, SeveritySummary } from "@/types/pipeline";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Pill, PillIndicator, PillStatus } from "@/components/ui/pill";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock3,
  ExternalLink,
  GitBranch,
  GitCommit,
  Github,
  Loader2,
  RefreshCcw,
  Search,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const STAGE_ORDER = [
  "quality_gate",
  "compiler_check",
  "ai_remediation",
  "final_verification",
] as const;

const STAGE_LABELS: Record<string, string> = {
  quality_gate: "Quality",
  compiler_check: "Compiler",
  ai_remediation: "AI fix",
  final_verification: "Final",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
  error: "Error",
  skipped: "Skipped",
  needs_human: "Needs human",
  completed: "Completed",
  waiting: "Waiting",
};

type StatusTone = "success" | "error" | "warning" | "info";

function statusTone(status?: string | null): StatusTone {
  switch ((status || "").toLowerCase()) {
    case "passed":
    case "completed":
    case "success":
      return "success";
    case "failed":
    case "error":
    case "blocked":
      return "error";
    case "needs_human":
    case "pending":
      return "warning";
    case "running":
      return "info";
    default:
      return "info";
  }
}

function statusText(status?: string | null) {
  const key = (status || "waiting").toLowerCase();
  return STATUS_LABELS[key] || key.replace(/_/g, " ");
}

function shortSha(value?: string | null) {
  if (!value) return "-";
  return value.length > 8 ? value.slice(0, 8) : value;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  
  let parsedValue = value;
  if (parsedValue.includes(" ") && !parsedValue.includes("T")) {
    parsedValue = parsedValue.replace(" ", "T");
  }
  
  const timePart = parsedValue.split("T")[1];
  if (timePart && !timePart.includes("Z") && !timePart.includes("+") && !timePart.includes("-")) {
    parsedValue += "Z";
  }

  const date = new Date(parsedValue);
  if (Number.isNaN(date.getTime())) return "-";
  
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function numberFromSummary(summary: SeveritySummary | undefined, key: string) {
  const value = summary?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stageMap(run: PipelineRun) {
  const map = new Map<string, PipelineStage>();
  for (const stage of run.stages || []) {
    map.set(stage.stage_name, stage);
  }
  return map;
}

function stageStatus(run: PipelineRun, stageName: string) {
  return stageMap(run).get(stageName)?.status || "waiting";
}

function qualitySummary(run: PipelineRun): SeveritySummary {
  const qualityStage = stageMap(run).get("quality_gate");
  return run.quality_summary || qualityStage?.summary || {};
}

function artifactEntries(run: PipelineRun) {
  const artifacts = {
    ...(stageMap(run).get("quality_gate")?.artifacts || {}),
    ...(run.quality_artifacts || {}),
  };

  return Object.entries(artifacts)
    .filter(([, value]) => typeof value === "string" && value.trim())
    .slice(0, 3) as Array<[string, string]>;
}

function isHttpUrl(value: string) {
  return /^https?:\/\//i.test(value);
}

function stageIcon(stageName: string) {
  if (stageName === "quality_gate") return ShieldCheck;
  if (stageName === "compiler_check") return TerminalSquare;
  if (stageName === "ai_remediation") return Bot;
  return CheckCircle2;
}

function StagePill({ run, stageName }: Readonly<{ run: PipelineRun; stageName: string }>) {
  const status = stageStatus(run, stageName);
  const tone = statusTone(status);
  const Icon = stageIcon(stageName);

  return (
    <Pill themed className="border-zinc-200 bg-zinc-50">
      <PillStatus className="text-zinc-800">
        <Icon className="size-3.5 text-zinc-500" />
        {STAGE_LABELS[stageName] || stageName}
      </PillStatus>
      <PillIndicator variant={tone} pulse={status === "running"} />
      <span className="capitalize text-zinc-700">{statusText(status)}</span>
    </Pill>
  );
}

function OverallStatus({ status }: Readonly<{ status?: string | null }>) {
  const tone = statusTone(status);
  return (
    <Pill themed className="border-zinc-200 bg-zinc-50">
      <PillIndicator variant={tone} pulse={status === "running"} />
      <span className="font-medium capitalize text-zinc-800">{statusText(status)}</span>
    </Pill>
  );
}

function SeverityPill({
  label,
  value,
  tone,
}: Readonly<{ label: string; value: number; tone: StatusTone }>) {
  return (
    <Pill themed className="border-zinc-200 bg-zinc-50">
      <PillIndicator variant={value > 0 ? tone : "info"} />
      <span className="font-medium text-zinc-700">{label}</span>
      <span className="tabular-nums text-zinc-800">{value}</span>
    </Pill>
  );
}

function PipelineRow({ run }: Readonly<{ run: PipelineRun }>) {
  const summary = qualitySummary(run);
  const artifacts = artifactEntries(run);
  const lastRun = run.completed_at || run.started_at || run.created_at;

  return (
    <tr className="border-b border-zinc-200 align-top hover:bg-zinc-50">
      <td className="min-w-72 px-4 py-4">
        <div className="flex flex-col gap-2">
          <a
            href={`https://github.com/${run.repo}`}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-zinc-950 hover:text-blue-600"
          >
            {run.repo}
          </a>
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600">
            <span className="inline-flex items-center gap-1">
              <GitBranch className="size-3.5" />
              {run.branch || "-"}
            </span>
            <span className="inline-flex items-center gap-1">
              <GitCommit className="size-3.5" />
              {shortSha(run.commit_sha)}
            </span>
            <span>PR {run.pr_number ? `#${run.pr_number}` : "-"}</span>
          </div>
        </div>
      </td>
      <td className="px-4 py-4">
        <OverallStatus status={run.overall_status} />
      </td>
      <td className="min-w-[420px] px-4 py-4">
        <div className="flex flex-wrap gap-2">
          {STAGE_ORDER.map((stageName) => (
            <StagePill key={stageName} run={run} stageName={stageName} />
          ))}
        </div>
      </td>
      <td className="min-w-72 px-4 py-4">
        <div className="flex flex-wrap gap-2">
          <SeverityPill label="C" value={numberFromSummary(summary, "critical")} tone="error" />
          <SeverityPill label="H" value={numberFromSummary(summary, "high")} tone="error" />
          <SeverityPill label="M" value={numberFromSummary(summary, "medium")} tone="warning" />
          <SeverityPill label="L" value={numberFromSummary(summary, "low")} tone="info" />
        </div>
      </td>
      <td className="min-w-56 px-4 py-4">
        <div className="flex flex-col gap-2">
          {run.workflow_url ? (
            <a
              href={run.workflow_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:underline"
            >
              Workflow {run.workflow_run_id || "run"}
              <ExternalLink className="size-3.5" />
            </a>
          ) : (
            <span className="text-sm text-zinc-500">No workflow URL</span>
          )}
          <div className="flex flex-wrap gap-2">
            {artifacts.length ? (
              artifacts.map(([key, value]) =>
                isHttpUrl(value) ? (
                  <a
                    key={key}
                    href={value}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-700 hover:border-zinc-300 hover:bg-zinc-100"
                  >
                    {key.replace(/_/g, " ")}
                  </a>
                ) : (
                  <span
                    key={key}
                    className="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-600"
                    title={value}
                  >
                    {key.replace(/_/g, " ")}
                  </span>
                ),
              )
            ) : (
              <span className="text-xs text-zinc-500">No artifact links</span>
            )}
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-4 text-sm text-zinc-600">{formatDate(lastRun)}</td>
    </tr>
  );
}

function EmptyState({ message }: Readonly<{ message: string }>) {
  return (
    <div className="flex min-h-80 items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center">
      <div>
        <Clock3 className="mx-auto mb-3 size-8 text-zinc-400" />
        <h3 className="text-base font-semibold text-zinc-950">No pipeline runs found</h3>
        <p className="mt-1 max-w-md text-sm text-zinc-600">{message}</p>
      </div>
    </div>
  );
}

export function PipelineMonitorPanel() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [repoFilter, setRepoFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");

  async function loadRuns({ quiet = false }: { quiet?: boolean } = {}) {
    if (quiet) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const [nextRuns, authStatus] = await Promise.all([
        apiGet<PipelineRun[]>("/api/pipeline/runs?limit=100"),
        apiGet<AuthStatus>("/api/auth/status").catch(() => null),
      ]);
      setRuns(nextRuns);
      setAuth(authStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load pipeline runs.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadRuns();
  }, []);

  const repoOptions = useMemo(
    () => Array.from(new Set(runs.map((run) => run.repo))).sort(),
    [runs],
  );

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const repoMatch = repoFilter ? run.repo === repoFilter : true;
      const statusMatch = statusFilter ? run.overall_status === statusFilter : true;
      const stageMatch = stageFilter
        ? Boolean((run.stages || []).some((stage) => stage.stage_name === stageFilter))
        : true;
      const severityMatch = severityFilter
        ? numberFromSummary(qualitySummary(run), severityFilter) > 0
        : true;
      return repoMatch && statusMatch && stageMatch && severityMatch;
    });
  }, [repoFilter, runs, severityFilter, stageFilter, statusFilter]);

  const totals = useMemo(() => {
    return runs.reduce(
      (acc, run) => {
        const summary = qualitySummary(run);
        acc.critical += numberFromSummary(summary, "critical");
        acc.high += numberFromSummary(summary, "high");
        acc.medium += numberFromSummary(summary, "medium");
        acc.low += numberFromSummary(summary, "low");
        if (["failed", "blocked", "error", "needs_human"].includes(String(run.overall_status))) {
          acc.attention += 1;
        }
        return acc;
      },
      { attention: 0, critical: 0, high: 0, medium: 0, low: 0 },
    );
  }, [runs]);

  return (
    <>
        <div className="mb-6 grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Total runs</CardDescription>
              <CardTitle className="text-2xl">{runs.length}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Needs attention</CardDescription>
              <CardTitle className="text-2xl">{totals.attention}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Critical / high findings</CardDescription>
              <CardTitle className="text-2xl">{totals.critical + totals.high}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-3">
              <CardDescription>Medium / low findings</CardDescription>
              <CardTitle className="text-2xl">{totals.medium + totals.low}</CardTitle>
            </CardHeader>
          </Card>
        </div>

        <Card>
          <CardHeader className="border-b border-zinc-200">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <CardDescription className="font-semibold uppercase tracking-wide text-blue-600">
                  Autonomous quality pipeline
                </CardDescription>
                <CardTitle className="mt-2 text-xl">Pipeline Monitor</CardTitle>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
                  Tracks GitHub Actions quality reports, compiler status, AI remediation, final
                  verification, artifacts, and branch-protection evidence per repository.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <SeverityPill label="Critical" value={totals.critical} tone="error" />
                <SeverityPill label="High" value={totals.high} tone="error" />
                <SeverityPill label="Medium" value={totals.medium} tone="warning" />
                <SeverityPill label="Low" value={totals.low} tone="info" />
              </div>
            </div>
          </CardHeader>

          <CardContent className="p-0">
            <div className="border-b border-zinc-200 bg-zinc-50/70 p-4">
              <div className="grid gap-3 md:grid-cols-5">
                <label className="relative md:col-span-2">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400" />
                  <select
                    className="repo-select w-full pl-9"
                    value={repoFilter}
                    onChange={(event) => setRepoFilter(event.target.value)}
                  >
                    <option value="">All repositories</option>
                    {repoOptions.map((repo) => (
                      <option key={repo} value={repo}>
                        {repo}
                      </option>
                    ))}
                  </select>
                </label>
                <select
                  className="repo-select"
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                >
                  <option value="">Any status</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                  <option value="blocked">Blocked</option>
                  <option value="needs_human">Needs human</option>
                  <option value="error">Error</option>
                </select>
                <select
                  className="repo-select"
                  value={stageFilter}
                  onChange={(event) => setStageFilter(event.target.value)}
                >
                  <option value="">Any stage</option>
                  {STAGE_ORDER.map((stage) => (
                    <option key={stage} value={stage}>
                      {STAGE_LABELS[stage]}
                    </option>
                  ))}
                </select>
                <select
                  className="repo-select"
                  value={severityFilter}
                  onChange={(event) => setSeverityFilter(event.target.value)}
                >
                  <option value="">Any severity</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
            </div>

            {loading ? (
              <div className="flex min-h-96 items-center justify-center">
                <Loader2 className="mr-2 size-5 animate-spin text-zinc-500" />
                <span className="text-sm text-zinc-600">Loading pipeline runs</span>
              </div>
            ) : error ? (
              <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <div>
                    <p className="font-semibold">Pipeline Monitor unavailable</p>
                    <p className="mt-1">{error}</p>
                  </div>
                </div>
              </div>
            ) : filteredRuns.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1320px] text-left">
                  <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-600">
                    <tr>
                      <th className="px-4 py-3">Repository</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Stages</th>
                      <th className="px-4 py-3">Findings</th>
                      <th className="px-4 py-3">Reports</th>
                      <th className="px-4 py-3">Last run</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRuns.map((run) => (
                      <PipelineRow key={run.id} run={run} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-4">
                <EmptyState message="Change filters or wait for GitHub Actions to post a report to /api/quality/report." />
              </div>
            )}
          </CardContent>
        </Card>
    </>
  );
}

export function PipelineMonitor() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);

  useEffect(() => {
    void apiGet<AuthStatus>("/api/auth/status").then(setAuth).catch(() => setAuth(null));
  }, []);

  const signedInAs = auth?.user?.github_login || "GitHub session";

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-md bg-zinc-900 text-sm font-bold text-white">
              RI
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-lg font-semibold leading-tight text-zinc-950">Repo Intelligence</h1>
                <Pill themed className="border-blue-200 bg-blue-50 text-blue-700">
                  React preview
                </Pill>
              </div>
              <p className="text-sm text-zinc-600">Pipeline Monitor connected to existing APIs</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Pill themed className="border-zinc-200 bg-zinc-50">
              <Github className="size-3.5 text-zinc-600" />
              {signedInAs}
            </Pill>
            <Button variant="outline" onClick={() => window.location.assign("/")}>
              Classic dashboard
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1440px] px-6 py-6">
        <PipelineMonitorPanel />
      </main>
    </div>
  );
}
