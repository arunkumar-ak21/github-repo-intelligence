import {
  DataTable,
  DetailDrawer,
  EmptyState,
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
import type { AnalysisHistoryItem } from "@/types/pipeline";
import {
  Activity,
  Archive,
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  Download,
  ExternalLink,
  FileClock,
  FileJson,
  GitCompareArrows,
  History,
  Loader2,
  Package,
  Search,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";

type ToastType = "success" | "error" | "warning" | "info";
type ModuleFilter = "all" | "metadata" | "cicd" | "dependencies";

export interface AnalysisHistoryPageProps {
  readonly history: AnalysisHistoryItem[];
  readonly onOpen: (item: AnalysisHistoryItem) => void;
  readonly onDelete: (id: number) => Promise<void>;
  readonly onClear: () => Promise<void>;
  readonly onToast: (type: ToastType, message: string) => void;
}

type HistoryComparison = {
  healthDelta: number | null;
  starsDelta: number | null;
  forksDelta: number | null;
  issuesDelta: number | null;
  depsDelta: number | null;
  vulnerableDelta: number | null;
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  let parsedValue = value;
  if (parsedValue.includes(" ") && !parsedValue.includes("T")) parsedValue = parsedValue.replace(" ", "T");
  const timePart = parsedValue.split("T")[1];
  if (timePart && !timePart.includes("Z") && !timePart.includes("+") && !timePart.includes("-")) parsedValue += "Z";
  const date = new Date(parsedValue);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function compactNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Number(value));
}

function duration(value?: number | null) {
  if (!value) return "-";
  if (value < 1000) return `${value} ms`;
  const seconds = Math.round(value / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function scoreTone(score?: number | null) {
  if (score === null || score === undefined) return "neutral" as const;
  if (score >= 80) return "success" as const;
  if (score >= 55) return "warning" as const;
  return "error" as const;
}

function riskTone(risk?: string | null) {
  const value = String(risk || "").toLowerCase();
  if (value.includes("high") || value.includes("critical")) return "error" as const;
  if (value.includes("medium") || value.includes("moderate")) return "warning" as const;
  if (value.includes("low")) return "success" as const;
  return "neutral" as const;
}

function hasModule(item: AnalysisHistoryItem, filter: ModuleFilter) {
  if (filter === "all") return true;
  if (filter === "metadata") return Boolean(item.metadata);
  if (filter === "cicd") return Boolean(item.cicd || item.cicd_platforms?.length);
  if (filter === "dependencies") return Boolean(item.dependencies || item.total_dependencies || item.vulnerable_count || item.outdated_count);
  return true;
}

function dateMatches(item: AnalysisHistoryItem, filter: string) {
  if (!filter) return true;
  if (!item.analyzed_at) return false;
  const date = new Date(item.analyzed_at);
  if (Number.isNaN(date.getTime())) return false;
  return date.toISOString().slice(0, 10) === filter;
}

function numberDelta(next?: number | null, previous?: number | null) {
  if (next === null || next === undefined || previous === null || previous === undefined) return null;
  return Number(next) - Number(previous);
}

function compareRecords(next: AnalysisHistoryItem, previous: AnalysisHistoryItem): HistoryComparison {
  return {
    healthDelta: numberDelta(next.health_score, previous.health_score),
    starsDelta: numberDelta(next.stars, previous.stars),
    forksDelta: numberDelta(next.forks, previous.forks),
    issuesDelta: numberDelta(next.open_issues, previous.open_issues),
    depsDelta: numberDelta(next.total_dependencies, previous.total_dependencies),
    vulnerableDelta: numberDelta(next.vulnerable_count, previous.vulnerable_count),
  };
}

function DeltaPill({ value, inverse = false }: Readonly<{ value: number | null; inverse?: boolean }>) {
  if (value === null) return <StatusPill tone="neutral" label="No baseline" />;
  if (value === 0) return <StatusPill tone="neutral" label="No change" />;
  const isGood = inverse ? value < 0 : value > 0;
  const Icon = value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <StatusPill
      tone={isGood ? "success" : "warning"}
      label={<span className="inline-flex items-center gap-1"><Icon className="size-3.5" />{value > 0 ? "+" : ""}{compactNumber(value)}</span>}
    />
  );
}

function moduleBadges(item: AnalysisHistoryItem) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <StatusPill tone={item.metadata ? "success" : "neutral"} label="Metadata" />
      <StatusPill tone={item.cicd || item.cicd_platforms?.length ? "success" : "neutral"} label="CI/CD" />
      <StatusPill tone={item.dependencies || item.total_dependencies ? "success" : "neutral"} label="Dependencies" />
    </div>
  );
}

function safeSummary(record: AnalysisHistoryItem | null) {
  if (!record) return [];
  return [
    ["Repository", record.repo],
    ["Analyzed", formatDate(record.analyzed_at)],
    ["Language", record.language || "Unknown"],
    ["Health score", record.health_score ?? "N/A"],
    ["Risk", record.risk_level || "Unknown"],
    ["Stars", compactNumber(record.stars)],
    ["Forks", compactNumber(record.forks)],
    ["Open issues", compactNumber(record.open_issues)],
    ["Default branch", record.default_branch || "-"],
    ["License", record.license_name || "-"],
    ["CI/CD platforms", (record.cicd_platforms || []).join(", ") || "None"],
    ["Dependencies", compactNumber(record.total_dependencies)],
    ["Vulnerable", compactNumber(record.vulnerable_count)],
    ["Outdated", compactNumber(record.outdated_count)],
    ["Duration", duration(record.analysis_duration_ms)],
  ];
}

export function AnalysisHistoryPage({
  history,
  onOpen,
  onDelete,
  onClear,
  onToast,
}: AnalysisHistoryPageProps) {
  const [repoFilter, setRepoFilter] = useState("");
  const [moduleFilter, setModuleFilter] = useState<ModuleFilter>("all");
  const [dateFilter, setDateFilter] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<AnalysisHistoryItem | null>(null);
  const [compareLeftId, setCompareLeftId] = useState<number | "">("");
  const [compareRightId, setCompareRightId] = useState<number | "">("");
  const [loadingRecord, setLoadingRecord] = useState(false);

  const repos = useMemo(() => Array.from(new Set(history.map((item) => item.repo))).sort(), [history]);
  const filteredHistory = useMemo(() => {
    return history.filter((item) => {
      const repoMatch = repoFilter ? item.repo === repoFilter : true;
      return repoMatch && hasModule(item, moduleFilter) && dateMatches(item, dateFilter);
    });
  }, [dateFilter, history, moduleFilter, repoFilter]);

  const latest = history[0] || null;
  const selectedForCompare = useMemo(() => {
    const left = history.find((item) => item.id === compareLeftId) || null;
    const right = history.find((item) => item.id === compareRightId) || null;
    return { left, right, comparison: left && right ? compareRecords(left, right) : null };
  }, [compareLeftId, compareRightId, history]);

  async function openDetails(item: AnalysisHistoryItem) {
    setLoadingRecord(true);
    try {
      const record = await apiGet<AnalysisHistoryItem>(`/api/history/${item.id}`);
      setSelectedRecord(record);
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "Could not open historical result.");
    } finally {
      setLoadingRecord(false);
    }
  }

  async function deleteItem(item: AnalysisHistoryItem) {
    try {
      await onDelete(item.id);
      if (selectedRecord?.id === item.id) setSelectedRecord(null);
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "Could not delete history item.");
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <CardDescription className="font-semibold uppercase tracking-wide text-blue-600">
                Repository intelligence history
              </CardDescription>
              <CardTitle className="mt-2 text-2xl">Analysis History</CardTitle>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
                This page tracks metadata, CI/CD, and dependency intelligence snapshots. Pipeline execution history stays in Pipeline Monitor.
              </p>
            </div>
            <Button variant="outline" onClick={() => void onClear()} disabled={!history.length}>
              <Trash2 className="mr-2 size-4" />
              Clear History
            </Button>
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Saved analyses" value={history.length} hint="Tenant-scoped AnalysisHistory rows" tone="neutral" icon={Archive} />
        <MetricCard label="Repositories" value={repos.length} hint="Unique repositories analyzed" tone="neutral" icon={History} />
        <MetricCard label="Latest score" value={latest?.health_score ?? "N/A"} hint={latest?.repo || "No latest result"} tone={scoreTone(latest?.health_score)} icon={Activity} />
        <MetricCard label="Dependency risk" value={compactNumber(latest?.vulnerable_count)} hint="Vulnerable dependencies in latest analysis" tone={latest?.vulnerable_count ? "warning" : "success"} icon={ShieldAlert} />
      </div>

      <Card>
        <CardHeader>
          <SectionHeader
            eyebrow="Filters"
            title="Find an analysis snapshot"
            description="Filter by repository, analysis date, or module coverage. These are repository intelligence records only."
          />
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
            <select className="repo-select" value={repoFilter} onChange={(event) => setRepoFilter(event.target.value)}>
              <option value="">All repositories</option>
              {repos.map((repo) => <option key={repo} value={repo}>{repo}</option>)}
            </select>
            <select className="repo-select" value={moduleFilter} onChange={(event) => setModuleFilter(event.target.value as ModuleFilter)}>
              <option value="all">All modules</option>
              <option value="metadata">Metadata</option>
              <option value="cicd">CI/CD</option>
              <option value="dependencies">Dependencies</option>
            </select>
            <input className="repo-input" type="date" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)} />
            <Button variant="outline" onClick={() => { setRepoFilter(""); setModuleFilter("all"); setDateFilter(""); }}>
              <Search className="mr-2 size-4" />
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader
            eyebrow="Compare"
            title="Compare previous analyses"
            description="Pick two snapshots to see directional changes without exposing internal evidence objects."
            action={selectedForCompare.comparison ? <StatusPill tone="info" label="Comparison ready" /> : undefined}
          />
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 lg:grid-cols-2">
            <select className="repo-select" value={compareLeftId} onChange={(event) => setCompareLeftId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select newer/current analysis</option>
              {history.map((item) => (
                <option key={item.id} value={item.id}>{item.repo} - {formatDate(item.analyzed_at)}</option>
              ))}
            </select>
            <select className="repo-select" value={compareRightId} onChange={(event) => setCompareRightId(event.target.value ? Number(event.target.value) : "")}>
              <option value="">Select previous baseline</option>
              {history.map((item) => (
                <option key={item.id} value={item.id}>{item.repo} - {formatDate(item.analyzed_at)}</option>
              ))}
            </select>
          </div>
          {selectedForCompare.comparison ? (
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Health score</p>
                <div className="mt-2"><DeltaPill value={selectedForCompare.comparison.healthDelta} /></div>
              </div>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Dependencies</p>
                <div className="mt-2"><DeltaPill value={selectedForCompare.comparison.depsDelta} inverse /></div>
              </div>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Vulnerable deps</p>
                <div className="mt-2"><DeltaPill value={selectedForCompare.comparison.vulnerableDelta} inverse /></div>
              </div>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Stars</p>
                <div className="mt-2"><DeltaPill value={selectedForCompare.comparison.starsDelta} /></div>
              </div>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Forks</p>
                <div className="mt-2"><DeltaPill value={selectedForCompare.comparison.forksDelta} /></div>
              </div>
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Open issues</p>
                <div className="mt-2"><DeltaPill value={selectedForCompare.comparison.issuesDelta} inverse /></div>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader
            eyebrow="Analysis records"
            title="Saved repository intelligence"
            description="Open a record to load it into the module pages, or inspect a safe summary drawer."
            action={<StatusPill tone="neutral" label={`${filteredHistory.length} records`} />}
          />
        </CardHeader>
        <CardContent>
          {history.length ? (
            <DataTable<AnalysisHistoryItem>
              rows={filteredHistory}
              getRowKey={(item) => String(item.id)}
              empty="No analysis records match the current filters."
              columns={[
                {
                  key: "repo",
                  header: "Repository",
                  render: (item) => (
                    <div>
                      <p className="font-mono font-semibold text-zinc-950">{item.repo}</p>
                      <p className="mt-1 text-xs text-zinc-500">{formatDate(item.analyzed_at)}</p>
                    </div>
                  ),
                },
                {
                  key: "modules",
                  header: "Modules",
                  render: moduleBadges,
                },
                {
                  key: "health",
                  header: "Health",
                  render: (item) => (
                    <div className="flex flex-wrap gap-1.5">
                      <StatusPill tone={scoreTone(item.health_score)} label={item.health_score ?? "N/A"} />
                      <StatusPill tone={riskTone(item.risk_level)} label={item.risk_level || "Unknown"} />
                    </div>
                  ),
                },
                {
                  key: "metadata",
                  header: "Metadata",
                  render: (item) => (
                    <span className="text-sm text-zinc-700">
                      {item.language || "Unknown"} - {compactNumber(item.stars)} stars - {compactNumber(item.forks)} forks
                    </span>
                  ),
                },
                {
                  key: "dependencies",
                  header: "Dependencies",
                  render: (item) => (
                    <span className="text-sm text-zinc-700">
                      <strong className="text-zinc-950">{compactNumber(item.total_dependencies)}</strong> total - {compactNumber(item.vulnerable_count)} vulnerable - {compactNumber(item.outdated_count)} outdated
                    </span>
                  ),
                },
                {
                  key: "duration",
                  header: "Duration",
                  render: (item) => duration(item.analysis_duration_ms),
                },
                {
                  key: "actions",
                  header: "Actions",
                  render: (item) => (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => onOpen(item)}>
                        <ExternalLink className="mr-2 size-4" />
                        Open result
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => void openDetails(item)} disabled={loadingRecord}>
                        {loadingRecord ? <Loader2 className="mr-2 size-4 animate-spin" /> : <FileClock className="mr-2 size-4" />}
                        Summary
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => void deleteItem(item)}>
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  ),
                },
              ]}
            />
          ) : (
            <EmptyState
              icon={History}
              title="No repository intelligence history yet"
              message="Run an analysis first. Completed analyses are stored separately from pipeline execution history."
            />
          )}
        </CardContent>
      </Card>

      <DetailDrawer
        open={Boolean(selectedRecord)}
        title={selectedRecord?.repo || "Historical result"}
        description="Safe summary of the selected repository intelligence record. Raw payloads stay hidden; use exports when needed."
        onClose={() => setSelectedRecord(null)}
      >
        {selectedRecord ? (
          <div className="space-y-5">
            <Card>
              <CardHeader>
                <SectionHeader
                  eyebrow="Snapshot"
                  title="Historical result summary"
                  description="This is the database-backed repository intelligence snapshot."
                  action={<StatusPill tone={scoreTone(selectedRecord.health_score)} label={`Health ${selectedRecord.health_score ?? "N/A"}`} />}
                />
              </CardHeader>
              <CardContent>
                <div className="grid gap-3 sm:grid-cols-2">
                  {safeSummary(selectedRecord).map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
                      <p className="mt-1 break-words text-sm font-semibold text-zinc-950">{value}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <SectionHeader
                  eyebrow="Coverage"
                  title="Modules included"
                  description="The historical record can be reopened into Overview, CI/CD, and Dependencies module pages."
                />
              </CardHeader>
              <CardContent>{moduleBadges(selectedRecord)}</CardContent>
            </Card>

            <Card>
              <CardHeader>
                <SectionHeader
                  eyebrow="Exports"
                  title="Download report artifacts"
                  description="Exports are intentional actions. Large internal objects are not rendered in the dashboard UI."
                />
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <a href={`/api/history/${selectedRecord.id}/export?format=json`}>
                    <FileJson className="mr-2 size-4" />
                    JSON export
                  </a>
                </Button>
                <Button asChild variant="outline">
                  <a href={`/api/history/${selectedRecord.id}/export?format=markdown`}>
                    <Download className="mr-2 size-4" />
                    Markdown export
                  </a>
                </Button>
                <Button onClick={() => onOpen(selectedRecord)}>
                  <GitCompareArrows className="mr-2 size-4" />
                  Open in modules
                </Button>
              </CardContent>
            </Card>

            <p className="text-xs leading-5 text-zinc-500">
              Raw metadata, CI/CD, and dependency JSON is intentionally not displayed here to avoid leaking backend evidence into the client UI.
            </p>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
