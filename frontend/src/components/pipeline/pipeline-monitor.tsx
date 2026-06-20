import {
  DataTable,
  DetailDrawer,
  EmptyState,
  FindingCard,
  MetricCard,
  SectionHeader,
  StatusPill,
} from "@/components/common/module-ui";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { apiGet } from "@/lib/api";
import type {
  AuthStatus,
  PipelineRun,
  PipelineStage,
  PipelineStageFinding,
  SetupRepository,
  SeveritySummary,
} from "@/types/pipeline";
import {
  AlertCircle,
  Archive,
  Bot,
  CheckCircle2,
  Clock3,
  Download,
  Eye,
  ExternalLink,
  FileJson,
  FileText,
  GitBranch,
  GitCommit,
  Github,
  Loader2,
  RefreshCcw,
  RotateCcw,
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
  quality_gate: "Quality gate",
  compiler_check: "Compiler check",
  ai_remediation: "AI remediation",
  final_verification: "Final verification",
  repo_intelligence: "Repo intelligence",
};

type Tone = "success" | "warning" | "error" | "info" | "neutral";

function statusTone(status?: string | null): Tone {
  const value = String(status || "").toLowerCase();
  if (["passed", "completed", "success", "active"].includes(value)) return "success";
  if (["failed", "blocked", "error"].includes(value)) return "error";
  if (["needs_human", "pending", "waiting"].includes(value)) return "warning";
  if (["running", "skipped"].includes(value)) return "info";
  return "neutral";
}

function statusText(status?: string | null) {
  const value = String(status || "waiting");
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
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

function formatDuration(ms?: number | null) {
  if (!ms || ms < 0) return "-";
  if (ms < 1000) return `${ms} ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
}

function stageMap(run?: PipelineRun | null) {
  const map = new Map<string, PipelineStage>();
  for (const stage of run?.stages || []) map.set(stage.stage_name, stage);
  return map;
}

function stageStatus(run: PipelineRun | null | undefined, stageName: string) {
  return stageMap(run).get(stageName)?.status || "waiting";
}

function stageIcon(stageName: string) {
  if (stageName === "quality_gate") return ShieldCheck;
  if (stageName === "compiler_check") return TerminalSquare;
  if (stageName === "ai_remediation") return Bot;
  if (stageName === "final_verification") return CheckCircle2;
  return Clock3;
}

function qualitySummary(run?: PipelineRun | null): SeveritySummary {
  const qualityStage = stageMap(run).get("quality_gate");
  return run?.quality_summary || qualityStage?.summary || {};
}

function numberFromSummary(summary: SeveritySummary | undefined, key: string) {
  const value = summary?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function collectArtifacts(run?: PipelineRun | null) {
  const entries: Array<{ stage: string; label: string; value: string }> = [];
  for (const stage of run?.stages || []) {
    for (const [key, value] of Object.entries(stage.artifacts || {})) {
      if (typeof value === "string" && value.trim()) {
        entries.push({ stage: stage.stage_name, label: key.replace(/_/g, " "), value });
      }
    }
  }
  for (const [key, value] of Object.entries(run?.quality_artifacts || {})) {
    if (typeof value === "string" && value.trim()) {
      entries.push({ stage: "quality_gate", label: key.replace(/_/g, " "), value });
    }
  }
  return entries;
}

function collectFindings(run?: PipelineRun | null) {
  const findings: Array<PipelineStageFinding & { stage_name: string }> = [];
  for (const stage of run?.stages || []) {
    for (const finding of stage.findings || []) findings.push({ ...finding, stage_name: stage.stage_name });
  }
  for (const finding of run?.quality_findings || []) {
    findings.push({ ...finding, stage_name: "quality_gate" });
  }
  const rank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  return findings.sort((a, b) => {
    const left = rank[String(a.severity || "").toLowerCase()] ?? 9;
    const right = rank[String(b.severity || "").toLowerCase()] ?? 9;
    return left - right;
  });
}

function setupForRun(run: PipelineRun | null, repos: SetupRepository[]) {
  if (!run) return null;
  return repos.find((repo) => repo.full_name === run.repo) || null;
}

function isHttpUrl(value: string) {
  return /^https?:\/\//i.test(value);
}

function stageLabel(stageName?: string | null) {
  return STAGE_LABELS[String(stageName || "")] || statusText(stageName || "unknown");
}

function safeReportValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  return String(value).replace(/\r?\n/g, " ").trim();
}

function markdownCell(value: unknown) {
  return safeReportValue(value).replace(/\|/g, "\\|");
}

function markdownTable(headers: string[], rows: unknown[][]) {
  const header = `| ${headers.map(markdownCell).join(" | ")} |`;
  const divider = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((row) => `| ${row.map(markdownCell).join(" | ")} |`);
  return [header, divider, ...body].join("\n");
}

function reportFileBase(run: PipelineRun) {
  const repo = (run.repo || "repository").replace(/[^a-zA-Z0-9._-]+/g, "-");
  return `arya-pipeline-${repo}-${shortSha(run.commit_sha)}`;
}

function safeReportPayload(run: PipelineRun) {
  const findings = collectFindings(run).map((finding) => ({
    stage: finding.stage_name,
    scanner: finding.scanner || null,
    severity: finding.severity || null,
    rule_id: finding.rule_id || null,
    title: finding.title || null,
    message: finding.message || null,
    file_path: finding.file_path || null,
    line_number: finding.line_number || null,
    recommendation: finding.recommendation || null,
  }));

  return {
    generated_at: new Date().toISOString(),
    report_type: "pipeline_monitor_summary",
    repo: run.repo,
    branch: run.branch || null,
    commit_sha: run.commit_sha || null,
    pr_number: run.pr_number || null,
    workflow_run_id: run.workflow_run_id || null,
    workflow_url: run.workflow_url || null,
    overall_status: run.overall_status || null,
    started_at: run.started_at || null,
    completed_at: run.completed_at || null,
    quality_summary: qualitySummary(run),
    stages: (run.stages || []).map((stage) => ({
      stage_name: stage.stage_name,
      status: stage.status || null,
      blocking: Boolean(stage.blocking),
      started_at: stage.started_at || null,
      completed_at: stage.completed_at || null,
      duration_ms: stage.duration_ms || null,
      summary: stage.summary || {},
      artifacts: stage.artifacts || {},
      findings_count: stage.findings?.length || 0,
    })),
    findings,
    artifacts: collectArtifacts(run),
  };
}

function buildPipelineReportMarkdown(run: PipelineRun) {
  const summary = qualitySummary(run);
  const stages = run.stages || [];
  const findings = collectFindings(run);
  const artifacts = collectArtifacts(run);

  const stageRows = stages.length
    ? stages.map((stage) => [
        stageLabel(stage.stage_name),
        statusText(stage.status),
        stage.blocking ? "Yes" : "No",
        formatDuration(stage.duration_ms),
        formatDate(stage.completed_at || stage.started_at),
      ])
    : [["No stages reported", "-", "-", "-", "-"]];

  const findingRows = findings.length
    ? findings.map((finding) => [
        stageLabel(finding.stage_name),
        finding.severity || "info",
        finding.scanner || "-",
        finding.rule_id || "-",
        finding.file_path ? `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ""}` : "-",
        finding.title || finding.message || "Pipeline finding",
        finding.recommendation || "-",
      ])
    : [["-", "-", "-", "-", "-", "No findings stored for this run", "-"]];

  const artifactRows = artifacts.length
    ? artifacts.map((artifact) => [
        stageLabel(artifact.stage),
        artifact.label,
        artifact.value,
      ])
    : [["-", "No artifacts stored", "-"]];

  return [
    "# Arya Pipeline Report",
    "",
    "## Verdict",
    `- Repository: ${safeReportValue(run.repo)}`,
    `- Branch: ${safeReportValue(run.branch)}`,
    `- Commit: ${safeReportValue(run.commit_sha)}`,
    `- Pull request: ${run.pr_number ? `#${run.pr_number}` : "-"}`,
    `- Workflow run: ${safeReportValue(run.workflow_run_id)}`,
    `- Workflow URL: ${safeReportValue(run.workflow_url)}`,
    `- Overall status: ${statusText(run.overall_status)}`,
    `- Started: ${formatDate(run.started_at)}`,
    `- Completed: ${formatDate(run.completed_at)}`,
    `- Generated: ${new Date().toISOString()}`,
    "",
    "## Quality Summary",
    `- Total findings: ${numberFromSummary(summary, "total_findings")}`,
    `- Critical: ${numberFromSummary(summary, "critical")}`,
    `- High: ${numberFromSummary(summary, "high")}`,
    `- Medium: ${numberFromSummary(summary, "medium")}`,
    `- Low: ${numberFromSummary(summary, "low")}`,
    `- Files scanned: ${numberFromSummary(summary, "files_scanned")}`,
    `- Duration seconds: ${numberFromSummary(summary, "duration_seconds")}`,
    "",
    "## Stage Results",
    markdownTable(["Stage", "Status", "Blocking", "Duration", "Updated"], stageRows),
    "",
    "## Findings",
    "Secret values and raw scanner payloads are intentionally excluded from this report.",
    "",
    markdownTable(["Stage", "Severity", "Scanner", "Rule", "File", "Finding", "Recommendation"], findingRows),
    "",
    "## Artifacts",
    "Use the GitHub Actions run for the full uploaded artifact ZIP. This dashboard report contains the safe normalized summary.",
    "",
    markdownTable(["Stage", "Artifact", "Value"], artifactRows),
    "",
  ].join("\n");
}

function downloadTextFile(filename: string, contents: string, mimeType: string) {
  const blob = new Blob([contents], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function downloadRunReport(run: PipelineRun, format: "markdown" | "json") {
  if (format === "json") {
    downloadTextFile(
      `${reportFileBase(run)}.json`,
      JSON.stringify(safeReportPayload(run), null, 2),
      "application/json",
    );
    return;
  }
  downloadTextFile(`${reportFileBase(run)}.md`, buildPipelineReportMarkdown(run), "text/markdown");
}

function RunTimeline({ run }: Readonly<{ run: PipelineRun | null }>) {
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          eyebrow="Run timeline"
          title="Required enforcement stages"
          description="The workflow should progress from quality gate to compiler check, then into remediation only when compiler fails."
        />
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 md:grid-cols-4">
          {STAGE_ORDER.map((stageName, index) => {
            const Icon = stageIcon(stageName);
            const stage = stageMap(run).get(stageName);
            const tone = statusTone(stageStatus(run, stageName));
            return (
              <div key={stageName} className="relative rounded-lg border border-zinc-200 bg-white p-4">
                {index > 0 ? <div className="absolute -left-3 top-8 hidden h-px w-6 bg-zinc-200 md:block" /> : null}
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-9 place-items-center rounded-md border border-zinc-200 bg-zinc-50 text-zinc-700">
                    <Icon className="size-4" />
                  </span>
                  <StatusPill tone={tone} pulse={stage?.status === "running"} label={statusText(stage?.status)} />
                </div>
                <h3 className="mt-4 text-sm font-semibold text-zinc-950">{STAGE_LABELS[stageName]}</h3>
                <p className="mt-1 text-xs leading-5 text-zinc-600">
                  {stage ? `${formatDuration(stage.duration_ms)} - ${stage.blocking ? "Blocking" : "Non-blocking"}` : "Waiting for report"}
                </p>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function LatestRunSummary({
  run,
  setupRepo,
  onRefresh,
  refreshing,
}: Readonly<{
  run: PipelineRun | null;
  setupRepo: SetupRepository | null;
  onRefresh: () => void;
  refreshing: boolean;
}>) {
  const summary = qualitySummary(run);
  const status = run?.overall_status || "waiting";
  const setupReady = setupRepo?.setup_status === "active";

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <CardDescription className="font-semibold uppercase tracking-wide text-blue-600">
              Latest enforcement run
            </CardDescription>
            <CardTitle className="mt-2 text-2xl">
              {run ? run.repo : "No pipeline run yet"}
            </CardTitle>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-zinc-600">
              <Pill className="border-zinc-200 bg-zinc-50 font-mono text-zinc-700">
                <GitBranch className="size-3.5" />
                {run?.branch || "-"}
              </Pill>
              <Pill className="border-zinc-200 bg-zinc-50 font-mono text-zinc-700">
                <GitCommit className="size-3.5" />
                {shortSha(run?.commit_sha)}
              </Pill>
              <Pill className="border-zinc-200 bg-zinc-50 text-zinc-700">
                PR {run?.pr_number ? `#${run.pr_number}` : "-"}
              </Pill>
              <Pill className="border-zinc-200 bg-zinc-50 text-zinc-700">
                Run {run?.workflow_run_id || "-"}
              </Pill>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill tone={statusTone(status)} pulse={status === "running"} label={statusText(status)} />
            <StatusPill
              tone={setupReady ? "success" : "warning"}
              label={setupReady ? "Setup ready" : "Setup needs check"}
            />
            <Button variant="outline" onClick={onRefresh} disabled={refreshing}>
              {refreshing ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCcw className="mr-2 size-4" />}
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-4">
          <MetricCard
            label="Critical"
            value={numberFromSummary(summary, "critical")}
            hint="Quality findings"
            tone={numberFromSummary(summary, "critical") ? "error" : "neutral"}
            icon={AlertCircle}
          />
          <MetricCard
            label="High"
            value={numberFromSummary(summary, "high")}
            hint="Quality findings"
            tone={numberFromSummary(summary, "high") ? "error" : "neutral"}
            icon={ShieldCheck}
          />
          <MetricCard
            label="Total findings"
            value={numberFromSummary(summary, "total_findings")}
            hint={`${numberFromSummary(summary, "files_scanned")} files scanned`}
            tone={numberFromSummary(summary, "total_findings") ? "warning" : "success"}
            icon={Search}
          />
          <MetricCard
            label="Last update"
            value={formatDate(run?.completed_at || run?.started_at || run?.created_at)}
            hint="GitHub Actions report time"
            tone="neutral"
            icon={Clock3}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function RunActions({
  run,
  setupRepo,
  onOpenReport,
  onDownloadReport,
  reportLoading,
}: Readonly<{
  run: PipelineRun | null;
  setupRepo: SetupRepository | null;
  onOpenReport: (run: PipelineRun) => void;
  onDownloadReport: (run: PipelineRun) => void;
  reportLoading: boolean;
}>) {
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          eyebrow="Retry and setup"
          title="Operational links"
          description="Open a readable report here. Use GitHub Actions for reruns and full artifact ZIP downloads."
        />
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {run ? (
          <>
            <Button variant="default" onClick={() => onOpenReport(run)} disabled={reportLoading}>
              {reportLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Eye className="mr-2 size-4" />}
              Open report
            </Button>
            <Button variant="outline" onClick={() => onDownloadReport(run)} disabled={reportLoading}>
              <Download className="mr-2 size-4" />
              Download report
            </Button>
          </>
        ) : (
          <Button variant="outline" disabled>
            <FileText className="mr-2 size-4" />
            No report yet
          </Button>
        )}
        {run?.workflow_url ? (
          <Button asChild variant="outline">
            <a href={run.workflow_url} target="_blank" rel="noreferrer">
              <RotateCcw className="mr-2 size-4" />
              Open GitHub run
            </a>
          </Button>
        ) : (
          <Button variant="outline" disabled>
            <RotateCcw className="mr-2 size-4" />
            No workflow run
          </Button>
        )}
        {run?.repo ? (
          <Button asChild variant="outline">
            <a href={`https://github.com/${run.repo}/actions`} target="_blank" rel="noreferrer">
              <Github className="mr-2 size-4" />
              Repository actions
            </a>
          </Button>
        ) : null}
        <Button asChild variant={setupRepo?.setup_status === "active" ? "outline" : "default"}>
          <a href="/react/dashboard/repo-setup">
            <ShieldCheck className="mr-2 size-4" />
            Open Repo Setup
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}

function ReportDrawer({
  run,
  open,
  onClose,
  onDownloadMarkdown,
  onDownloadJson,
}: Readonly<{
  run: PipelineRun | null;
  open: boolean;
  onClose: () => void;
  onDownloadMarkdown: () => void;
  onDownloadJson: () => void;
}>) {
  const summary = qualitySummary(run);
  const findings = collectFindings(run);
  const artifacts = collectArtifacts(run);

  return (
    <DetailDrawer
      open={open}
      title={run ? `${run.repo} pipeline report` : "Pipeline report"}
      description="Readable enforcement summary generated from normalized dashboard data. Raw scanner payloads and secret values are not included."
      onClose={onClose}
    >
      {run ? (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Button onClick={onDownloadMarkdown}>
              <Download className="mr-2 size-4" />
              Download Markdown
            </Button>
            <Button variant="outline" onClick={onDownloadJson}>
              <FileJson className="mr-2 size-4" />
              Download safe JSON
            </Button>
            {run.workflow_url ? (
              <Button asChild variant="outline">
                <a href={run.workflow_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-2 size-4" />
                  Open GitHub run
                </a>
              </Button>
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard label="Status" value={statusText(run.overall_status)} tone={statusTone(run.overall_status)} icon={ShieldCheck} />
            <MetricCard label="Findings" value={numberFromSummary(summary, "total_findings")} hint={`${numberFromSummary(summary, "critical") + numberFromSummary(summary, "high")} critical/high`} tone={numberFromSummary(summary, "total_findings") ? "warning" : "success"} icon={AlertCircle} />
          </div>

          <Card>
            <CardHeader>
              <SectionHeader
                eyebrow="Run identity"
                title="Repository and workflow"
                description="This metadata connects the dashboard report back to the exact GitHub Actions run."
              />
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="font-semibold text-zinc-950">Repository</dt>
                  <dd className="mt-1 font-mono text-zinc-600">{run.repo}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-zinc-950">Branch</dt>
                  <dd className="mt-1 font-mono text-zinc-600">{run.branch || "-"}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-zinc-950">Commit</dt>
                  <dd className="mt-1 font-mono text-zinc-600">{run.commit_sha || "-"}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-zinc-950">Workflow run</dt>
                  <dd className="mt-1 font-mono text-zinc-600">{run.workflow_run_id || "-"}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <SectionHeader eyebrow="Stages" title="Stage results" />
            </CardHeader>
            <CardContent>
              <DataTable<PipelineStage>
                rows={run.stages || []}
                getRowKey={(stage, index) => `${stage.stage_name}-${index}`}
                empty="No stage results were stored for this report."
                columns={[
                  {
                    key: "stage",
                    header: "Stage",
                    render: (stage) => stageLabel(stage.stage_name),
                  },
                  {
                    key: "status",
                    header: "Status",
                    render: (stage) => <StatusPill tone={statusTone(stage.status)} label={statusText(stage.status)} />,
                  },
                  {
                    key: "blocking",
                    header: "Blocking",
                    render: (stage) => (stage.blocking ? "Yes" : "No"),
                  },
                  {
                    key: "duration",
                    header: "Duration",
                    render: (stage) => formatDuration(stage.duration_ms),
                  },
                ]}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <SectionHeader
                eyebrow="Findings"
                title="Top findings"
                description={findings.length > 20 ? "Showing the first 20 findings here. Download the report for the full stored finding list." : "Safe, normalized findings only."}
                action={<StatusPill tone={findings.length ? "warning" : "success"} label={`${findings.length} findings`} />}
              />
            </CardHeader>
            <CardContent>
              {findings.length ? (
                <div className="space-y-3">
                  {findings.slice(0, 20).map((finding, index) => (
                    <FindingCard
                      key={`${finding.stage_name}-${finding.rule_id}-${finding.file_path}-${index}`}
                      title={finding.title || finding.rule_id || "Pipeline finding"}
                      severity={finding.severity || "info"}
                      message={finding.message || undefined}
                      file={finding.file_path ? `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ""}` : undefined}
                      ruleId={`${stageLabel(finding.stage_name)}${finding.scanner ? ` - ${finding.scanner}` : ""}`}
                      recommendation={finding.recommendation || undefined}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState icon={ShieldCheck} title="No findings in this report" message="The workflow may still have logs in GitHub Actions if a stage failed without normalized findings." />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <SectionHeader
                eyebrow="Artifacts"
                title="Report artifacts"
                description="Dashboard downloads are generated here. The full uploaded ZIP remains in GitHub Actions."
                action={run.workflow_url ? (
                  <Button asChild variant="outline" size="sm">
                    <a href={run.workflow_url} target="_blank" rel="noreferrer">
                      <Archive className="mr-2 size-4" />
                      Open GitHub artifacts
                    </a>
                  </Button>
                ) : undefined}
              />
            </CardHeader>
            <CardContent>
              {artifacts.length ? (
                <div className="space-y-2">
                  {artifacts.map((artifact, index) => (
                    <div key={`${artifact.stage}-${artifact.label}-${index}`} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2 text-sm">
                      <div className="min-w-0">
                        <p className="font-semibold text-zinc-950">{artifact.label}</p>
                        <p className="truncate font-mono text-xs text-zinc-500">{artifact.value}</p>
                      </div>
                      <StatusPill tone="neutral" label={stageLabel(artifact.stage)} />
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState icon={Archive} title="No artifact names stored" message="Open the GitHub Actions run if artifact upload completed but the dashboard payload did not include artifact metadata." />
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}
    </DetailDrawer>
  );
}

function ArtifactLinks({ run }: Readonly<{ run: PipelineRun | null }>) {
  const artifacts = collectArtifacts(run);
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          eyebrow="Evidence"
          title="Artifacts and report links"
          description="Links and artifact names generated by GitHub Actions. Raw backend payloads are intentionally not exposed here."
          action={
            <div className="flex flex-wrap gap-2">
              <StatusPill tone="neutral" label={`${artifacts.length} links`} />
              {run?.workflow_url ? (
                <Button asChild variant="outline" size="sm">
                  <a href={run.workflow_url} target="_blank" rel="noreferrer">
                    <Archive className="mr-2 size-4" />
                    GitHub artifacts
                  </a>
                </Button>
              ) : null}
            </div>
          }
        />
      </CardHeader>
      <CardContent>
        {artifacts.length ? (
          <div className="grid gap-3 md:grid-cols-2">
            {artifacts.map((artifact, index) => (
              <div key={`${artifact.stage}-${artifact.label}-${index}`} className="rounded-lg border border-zinc-200 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                      {STAGE_LABELS[artifact.stage] || artifact.stage}
                    </p>
                    <p className="mt-1 truncate text-sm font-semibold text-zinc-950">{artifact.label}</p>
                    <p className="mt-1 truncate font-mono text-xs text-zinc-500">{artifact.value}</p>
                  </div>
                  {isHttpUrl(artifact.value) ? (
                    <Button asChild size="sm" variant="outline">
                      <a href={artifact.value} target="_blank" rel="noreferrer">
                        <ExternalLink className="size-4" />
                      </a>
                    </Button>
                  ) : (
                    <Archive className="mt-1 size-4 text-zinc-400" />
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Archive}
            title="No report artifacts yet"
            message="Artifacts appear after GitHub Actions uploads quality, compiler, or workflow summary reports."
          />
        )}
      </CardContent>
    </Card>
  );
}

export function PipelineMonitorPanel() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [setupRepos, setSetupRepos] = useState<SetupRepository[]>([]);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedRun, setSelectedRun] = useState<PipelineRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [reportRun, setReportRun] = useState<PipelineRun | null>(null);
  const [reportLoadingId, setReportLoadingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [repoFilter, setRepoFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  async function loadRuns({ quiet = false }: { quiet?: boolean } = {}) {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const [nextRuns, nextRepos, authStatus] = await Promise.all([
        apiGet<PipelineRun[]>("/api/pipeline/runs?limit=100"),
        apiGet<SetupRepository[]>("/api/setup/repositories").catch(() => []),
        apiGet<AuthStatus>("/api/auth/status").catch(() => null),
      ]);
      setRuns(nextRuns);
      setSetupRepos(nextRepos);
      setAuth(authStatus);
      const nextSelected = selectedRunId && nextRuns.some((run) => run.id === selectedRunId)
        ? selectedRunId
        : nextRuns[0]?.id ?? null;
      setSelectedRunId(nextSelected);
      if (!nextSelected) setSelectedRun(null);
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

  useEffect(() => {
    if (!selectedRunId) return;
    let cancelled = false;
    setDetailsLoading(true);
    apiGet<PipelineRun>(`/api/pipeline/runs/${selectedRunId}`)
      .then((run) => {
        if (!cancelled) setSelectedRun(run);
      })
      .catch(() => {
        const fallback = runs.find((run) => run.id === selectedRunId) || null;
        if (!cancelled) setSelectedRun(fallback);
      })
      .finally(() => {
        if (!cancelled) setDetailsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runs, selectedRunId]);

  async function loadRunDetailsForReport(run: PipelineRun) {
    if (selectedRun?.id === run.id && (selectedRun.stages?.length || selectedRun.quality_findings?.length)) {
      return selectedRun;
    }
    const details = await apiGet<PipelineRun>(`/api/pipeline/runs/${run.id}`);
    if (selectedRunId === run.id) setSelectedRun(details);
    return details;
  }

  async function openRunReport(run: PipelineRun) {
    setReportLoadingId(run.id);
    try {
      const details = await loadRunDetailsForReport(run);
      setReportRun(details);
    } catch {
      setReportRun(run);
    } finally {
      setReportLoadingId(null);
    }
  }

  async function downloadRunReportWithDetails(run: PipelineRun, format: "markdown" | "json" = "markdown") {
    setReportLoadingId(run.id);
    try {
      const details = await loadRunDetailsForReport(run);
      downloadRunReport(details, format);
    } catch {
      downloadRunReport(run, format);
    } finally {
      setReportLoadingId(null);
    }
  }

  const repoOptions = useMemo(() => Array.from(new Set(runs.map((run) => run.repo))).sort(), [runs]);
  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const repoMatch = repoFilter ? run.repo === repoFilter : true;
      const statusMatch = statusFilter ? run.overall_status === statusFilter : true;
      return repoMatch && statusMatch;
    });
  }, [repoFilter, runs, statusFilter]);

  const selectedSetupRepo = setupForRun(selectedRun, setupRepos);
  const findings = collectFindings(selectedRun);

  if (loading) {
    return (
      <div className="flex min-h-96 items-center justify-center rounded-lg border border-zinc-200 bg-white">
        <Loader2 className="mr-2 size-5 animate-spin text-zinc-500" />
        <span className="text-sm text-zinc-600">Loading Pipeline Monitor</span>
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-5">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div>
                <p className="font-semibold">Pipeline Monitor unavailable</p>
                <p className="mt-1">{error}</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <LatestRunSummary
        run={selectedRun || runs[0] || null}
        setupRepo={selectedSetupRepo}
        onRefresh={() => void loadRuns({ quiet: true })}
        refreshing={refreshing}
      />

      <RunTimeline run={selectedRun} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(340px,0.8fr)]">
        <Card>
          <CardHeader>
            <SectionHeader
              eyebrow="Stages"
              title="Stage status table"
              description="The same stage contract is used for quality, compiler, AI remediation, and final verification."
              action={detailsLoading ? <StatusPill tone="info" pulse label="Loading details" /> : undefined}
            />
          </CardHeader>
          <CardContent>
            <DataTable<PipelineStage>
              rows={selectedRun?.stages || []}
              getRowKey={(stage, index) => `${stage.stage_name}-${index}`}
              empty="No stage reports have been received for this run."
              columns={[
                {
                  key: "stage",
                  header: "Stage",
                  render: (stage) => {
                    const Icon = stageIcon(stage.stage_name);
                    return (
                      <div className="flex items-center gap-2">
                        <Icon className="size-4 text-zinc-500" />
                        <span className="font-semibold text-zinc-950">{STAGE_LABELS[stage.stage_name] || stage.stage_name}</span>
                      </div>
                    );
                  },
                },
                {
                  key: "status",
                  header: "Status",
                  render: (stage) => <StatusPill tone={statusTone(stage.status)} pulse={stage.status === "running"} label={statusText(stage.status)} />,
                },
                {
                  key: "blocking",
                  header: "Blocking",
                  render: (stage) => <StatusPill tone={stage.blocking ? "error" : "neutral"} label={stage.blocking ? "Yes" : "No"} />,
                },
                {
                  key: "duration",
                  header: "Duration",
                  render: (stage) => formatDuration(stage.duration_ms),
                },
                {
                  key: "updated",
                  header: "Updated",
                  render: (stage) => formatDate(stage.completed_at || stage.started_at),
                },
              ]}
            />
          </CardContent>
        </Card>

        <RunActions
          run={selectedRun}
          setupRepo={selectedSetupRepo}
          onOpenReport={(run) => void openRunReport(run)}
          onDownloadReport={(run) => void downloadRunReportWithDetails(run)}
          reportLoading={Boolean(selectedRun && reportLoadingId === selectedRun.id)}
        />
      </div>

      <Card>
        <CardHeader>
          <SectionHeader
            eyebrow="Findings by run"
            title="Blocking evidence"
            description="Security and compiler findings are normalized into safe, redacted records before display."
            action={<StatusPill tone={findings.length ? "warning" : "success"} label={`${findings.length} findings`} />}
          />
        </CardHeader>
        <CardContent>
          {findings.length ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {findings.slice(0, 12).map((finding, index) => (
                <FindingCard
                  key={`${finding.stage_name}-${finding.rule_id}-${finding.file_path}-${index}`}
                  title={finding.title || finding.rule_id || "Pipeline finding"}
                  severity={finding.severity || "info"}
                  message={finding.message || undefined}
                  file={finding.file_path ? `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ""}` : undefined}
                  ruleId={`${STAGE_LABELS[finding.stage_name] || finding.stage_name}${finding.scanner ? ` - ${finding.scanner}` : ""}`}
                  recommendation={finding.recommendation || undefined}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={ShieldCheck}
              title="No blocking findings for this run"
              message="If a stage failed without findings, open the workflow artifact or GitHub Actions run for logs."
            />
          )}
        </CardContent>
      </Card>

      <ArtifactLinks run={selectedRun} />

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <SectionHeader
              eyebrow="Run history"
              title="Repository pipeline runs"
              description="Select a run to inspect its timeline, stage results, findings, and artifact links."
            />
            <div className="grid gap-2 sm:grid-cols-2">
              <select className="repo-select" value={repoFilter} onChange={(event) => setRepoFilter(event.target.value)}>
                <option value="">All repositories</option>
                {repoOptions.map((repo) => (
                  <option key={repo} value={repo}>{repo}</option>
                ))}
              </select>
              <select className="repo-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="">Any status</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="blocked">Blocked</option>
                <option value="error">Error</option>
                <option value="needs_human">Needs human</option>
                <option value="running">Running</option>
              </select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <DataTable<PipelineRun>
            rows={filteredRuns}
            getRowKey={(run) => String(run.id)}
            empty="No GitHub Actions reports have been posted yet."
            columns={[
              {
                key: "repo",
                header: "Repository",
                render: (run) => (
                  <button className="text-left" onClick={() => setSelectedRunId(run.id)}>
                    <span className="block font-semibold text-zinc-950 hover:text-blue-600">{run.repo}</span>
                    <span className="mt-1 block font-mono text-xs text-zinc-500">{shortSha(run.commit_sha)} - {run.branch || "-"}</span>
                  </button>
                ),
              },
              {
                key: "status",
                header: "Status",
                render: (run) => <StatusPill tone={statusTone(run.overall_status)} label={statusText(run.overall_status)} />,
              },
              {
                key: "checks",
                header: "Checks",
                render: (run) => (
                  <div className="flex flex-wrap gap-1.5">
                    {STAGE_ORDER.map((stageName) => (
                      <StatusPill
                        key={stageName}
                        tone={statusTone(stageStatus(run, stageName))}
                        label={STAGE_LABELS[stageName].replace(" ", " ")}
                      />
                    ))}
                  </div>
                ),
              },
              {
                key: "findings",
                header: "Findings",
                render: (run) => {
                  const summary = qualitySummary(run);
                  const total = numberFromSummary(summary, "total_findings");
                  const high = numberFromSummary(summary, "critical") + numberFromSummary(summary, "high");
                  return (
                    <span className="text-sm text-zinc-700">
                      <strong className="text-zinc-950">{total}</strong> total - {high} critical/high
                    </span>
                  );
                },
              },
              {
                key: "report",
                header: "Report",
                render: (run) => (
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => void openRunReport(run)} disabled={reportLoadingId === run.id}>
                      {reportLoadingId === run.id ? <Loader2 className="mr-2 size-3.5 animate-spin" /> : <Eye className="mr-2 size-3.5" />}
                      Open
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => void downloadRunReportWithDetails(run)} disabled={reportLoadingId === run.id}>
                      <Download className="mr-2 size-3.5" />
                      MD
                    </Button>
                  </div>
                ),
              },
              {
                key: "workflow",
                header: "Workflow",
                render: (run) => run.workflow_url ? (
                  <a href={run.workflow_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:underline">
                    Actions run
                    <ExternalLink className="size-3.5" />
                  </a>
                ) : <span className="text-zinc-500">No URL</span>,
              },
              {
                key: "time",
                header: "Last run",
                render: (run) => formatDate(run.completed_at || run.started_at || run.created_at),
              },
            ]}
          />
        </CardContent>
      </Card>

      <p className="text-xs text-zinc-500">
        Signed in as {auth?.user?.github_login || "current GitHub user"}. Pipeline Monitor shows normalized reports only; raw scanner values and secrets are not displayed.
      </p>

      <ReportDrawer
        open={Boolean(reportRun)}
        run={reportRun}
        onClose={() => setReportRun(null)}
        onDownloadMarkdown={() => reportRun ? downloadRunReport(reportRun, "markdown") : undefined}
        onDownloadJson={() => reportRun ? downloadRunReport(reportRun, "json") : undefined}
      />
    </div>
  );
}

export function PipelineMonitor() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-md bg-zinc-900 text-sm font-bold text-white">RI</div>
            <div>
              <h1 className="text-lg font-semibold leading-tight text-zinc-950">Repo Intelligence</h1>
              <p className="text-sm text-zinc-600">Pipeline Monitor</p>
            </div>
          </div>
          <Button variant="outline" onClick={() => window.location.assign("/")}>Classic dashboard</Button>
        </div>
      </header>
      <main className="mx-auto max-w-[1440px] px-6 py-6">
        <PipelineMonitorPanel />
      </main>
    </div>
  );
}
