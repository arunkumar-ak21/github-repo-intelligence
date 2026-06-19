import { PipelineMonitorPanel } from "@/components/pipeline/pipeline-monitor";
import { AnalysisHistoryPage } from "@/components/history/analysis-history-page";
import { RepoSetupPanel as RepoSetupPanelV2 } from "@/components/setup/repo-setup-panel";
import {
  DataTable as SharedDataTable,
  DetailDrawer as SharedDetailDrawer,
  DrawerButton,
  EmptyState as SharedEmptyState,
  FindingCard as SharedFindingCard,
  MetricCard as SharedMetricCard,
  PageHeader as SharedPageHeader,
  SectionHeader as SharedSectionHeader,
  StatusPill as SharedStatusPill,
  severityToTone,
} from "@/components/common/module-ui";
import { AnimatedAnalyzeButton } from "@/components/ui/animated-analyze-button";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuPortal,
} from "@/components/ui/dropdown-menu";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Pill, PillIndicator, PillStatus } from "@/components/ui/pill";
import { AnimatedActionButton } from "@/components/ui/animated-action-button";
import { HeroDashboardMockup } from "@/components/ui/hero-dashboard-mockup";
import DisplayCards from "@/components/ui/display-cards";
import { GlassEffect, GlassFilter } from "@/components/ui/glass-effect";
import { apiDelete, apiGet, apiPost, streamPost, type StreamEvent } from "@/lib/api";
import type {
  AnalysisHistoryItem,
  AnalysisPayload,
  AuthStatus,
  SetupRepository,
} from "@/types/pipeline";
import {
  AlertTriangle,
  BarChart3,
  Building2,
  Check,
  Clock3,
  Download,
  ExternalLink,
  FileJson,
  Github,
  History,
  Loader2,
  LogOut,
  Package,
  Play,
  RefreshCcw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  TerminalSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Trash2,
  Upload,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";

type TabKey = "overview" | "cicd" | "deps" | "pipeline" | "setup" | "history";
type ViewKey = "landing" | "dashboard";
type Toast = { id: number; type: "success" | "error" | "warning" | "info"; message: string };
type ProgressLine = { id: number; module: string; message: string; level?: string };

type ModuleConfig = {
  key: TabKey;
  route: string;
  label: string;
  shortLabel: string;
  icon: typeof BarChart3;
  eyebrow: string;
  title: string;
  description: string;
  responsibility: string;
};

const MODULES: ModuleConfig[] = [
  {
    key: "overview",
    route: "overview",
    label: "Overview",
    shortLabel: "Overview",
    icon: BarChart3,
    eyebrow: "Repository summary",
    title: "Repository overview",
    description: "Identity, README, contributors, commits, file tree, and attention summary.",
    responsibility: "Answer what this repository is, who works on it, and where deeper investigation should begin.",
  },
  {
    key: "cicd",
    route: "cicd",
    label: "CI/CD",
    shortLabel: "CI/CD",
    icon: TerminalSquare,
    eyebrow: "Workflow intelligence",
    title: "CI/CD analysis",
    description: "Workflow files, triggers, jobs, security findings, permissions, and normalized pipeline signals.",
    responsibility: "Show how code is built, tested, released, and where automation risk exists.",
  },
  {
    key: "deps",
    route: "dependencies",
    label: "Dependencies",
    shortLabel: "Deps",
    icon: Package,
    eyebrow: "Dependency health",
    title: "Dependency analysis",
    description: "Package inventory, ecosystem health, vulnerability alerts, outdated packages, and architecture map.",
    responsibility: "Explain supply-chain risk and package health without mixing it into repo metadata.",
  },
  {
    key: "pipeline",
    route: "pipeline",
    label: "Pipeline Monitor",
    shortLabel: "Pipeline",
    icon: ShieldCheck,
    eyebrow: "Quality enforcement",
    title: "Pipeline monitor",
    description: "Autonomous quality runs, stages, status checks, reports, artifacts, and remediation status.",
    responsibility: "Track mandatory GitHub Actions enforcement and quality-gate outcomes across monitored repositories.",
  },
  {
    key: "setup",
    route: "repo-setup",
    label: "Repo Setup",
    shortLabel: "Setup",
    icon: Settings,
    eyebrow: "Repository onboarding",
    title: "Repository setup",
    description: "GitHub App installation, monitored repos, workflow provisioning, secrets, and branch protection state.",
    responsibility: "Make repository onboarding and enforcement configuration visible and client-safe.",
  },
  {
    key: "history",
    route: "history",
    label: "History",
    shortLabel: "History",
    icon: History,
    eyebrow: "Audit trail",
    title: "Analysis history",
    description: "Past repository intelligence analyses, cached records, module summaries, and replay actions.",
    responsibility: "Keep repo intelligence history separate from pipeline execution history.",
  },
];

const TABS = MODULES;
const MODULE_BY_KEY = Object.fromEntries(MODULES.map((module) => [module.key, module])) as Record<TabKey, ModuleConfig>;
const MODULE_KEY_BY_ROUTE = Object.fromEntries(MODULES.map((module) => [module.route, module.key])) as Record<string, TabKey>;

function normalizeRepoSlug(value: string) {
  let slug = String(value || "").trim();
  if (!slug) return "";
  if (slug.startsWith("git@github.com:")) slug = slug.replace("git@github.com:", "");
  else if (slug.startsWith("ssh://git@github.com/")) slug = slug.replace("ssh://git@github.com/", "");
  else if (/^https?:\/\//i.test(slug)) {
    try {
      const url = new URL(slug);
      if (url.hostname.replace(/^www\./, "").toLowerCase() !== "github.com") return "";
      slug = url.pathname.replace(/^\/+|\/+$/g, "");
    } catch {
      return "";
    }
  } else {
    slug = slug.replace(/^(www\.)?github\.com\//i, "");
  }
  slug = slug.split("?")[0].split("#")[0].replace(/\.git$/i, "").replace(/^\/+|\/+$/g, "");
  const [owner, repo] = slug.split("/");
  if (!owner || !repo) return "";
  if (!/^[A-Za-z0-9_.-]+$/.test(owner) || !/^[A-Za-z0-9_.-]+$/.test(repo)) return "";
  return `${owner}/${repo}`;
}

function normalizeAnalysisPayload(payload: AnalysisPayload | null): AnalysisPayload | null {
  if (!payload) return null;
  const metadata = payload.metadata || payload.metadata_json || {};
  const cicd = payload.cicd || payload.cicd_json || {};
  const dependencies = payload.dependencies || payload.dependencies_json || {};
  const repo =
    normalizeRepoSlug(payload.repo || payload.repository || metadata.full_name || cicd.slug || "") ||
    payload.repo ||
    "";
  const history_id = payload.history_id ?? payload.id ?? null;
  return { ...payload, repo, metadata, cicd, dependencies, history_id };
}

function formatNumber(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0";
  return number.toLocaleString();
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
  if (Number.isNaN(date.getTime())) return String(value);

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function scoreTone(score?: number | null) {
  if (typeof score !== "number") return "info";
  if (score >= 80) return "success";
  if (score >= 60) return "warning";
  return "error";
}

function statusTone(status?: string | null) {
  const value = String(status || "").toLowerCase();
  if (["active", "provisioned", "completed", "passed", "success"].includes(value)) return "success";
  if (["pending", "pending_pull_request", "dry_run", "needs_attention", "discovered", "setup_pr_open", "cleanup_pr_open"].includes(value)) return "warning";
  if (["failed", "error", "blocked"].includes(value)) return "error";
  if (["ignored", "removed", "deprovisioned", "deprovisioning"].includes(value)) return "info";
  return "info";
}

function humanize(value?: string | null) {
  return String(value || "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function safeUserMessage(error: unknown, fallback: string) {
  const message = error instanceof Error ? error.message : "";
  if (
    message.includes("UNIQUE constraint failed") ||
    message.includes("IntegrityError") ||
    message.includes("SQLAlchemy") ||
    message.includes("transaction has been rolled back") ||
    message.includes("sqlite3")
  ) {
    return fallback;
  }
  return message || fallback;
}

type SyncInstallResult = {
  status?: string;
  installations?: Array<{
    installation_id?: number | string;
    synced_repository_count?: number;
    synced_repositories?: number;
    provisioned_repository_count?: number;
    provisioned_repositories?: number;
    skipped_repository_count?: number;
    skipped_repositories?: number;
    errors?: Array<{ stage?: string; message?: string }>;
  }>;
};

function buildSyncMessage(result: SyncInstallResult) {
  const installations = result.installations || [];
  const synced = installations.reduce((total, item) => total + Number(item.synced_repository_count ?? item.synced_repositories ?? 0), 0);
  const provisioned = installations.reduce((total, item) => total + Number(item.provisioned_repository_count ?? item.provisioned_repositories ?? 0), 0);
  const errors = installations.reduce((total, item) => total + Number(item.errors?.length || 0), 0);
  if (errors > 0) return `Repositories synced with ${errors} warning${errors === 1 ? "" : "s"}.`;
  if (synced || provisioned) return `Repositories synced. ${synced} repo${synced === 1 ? "" : "s"} checked, ${provisioned} configured.`;
  return "Repositories synced successfully.";
}

function normalizeTopics(value: unknown) {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

function getRepoInfo(data: AnalysisPayload | null) {
  return (
    data?.metadata_details?.repository ||
    data?.dependencies?.repo_info ||
    data?.cicd?.meta ||
    data?.metadata ||
    {}
  );
}

function getDependencies(data: AnalysisPayload | null) {
  const deps = data?.dependencies?.dependencies;
  return Array.isArray(deps) ? deps : [];
}

function getAlerts(data: AnalysisPayload | null) {
  const alerts = data?.dependencies?.dependabot_alerts;
  return Array.isArray(alerts) ? alerts : [];
}

function getHealth(data: AnalysisPayload | null) {
  return data?.dependencies?.health || {};
}

function routeFromLocation(): ViewKey {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/react/dashboard" || path.startsWith("/react/dashboard/")) return "dashboard";
  return "landing";
}

function moduleFromLocation(): TabKey {
  const path = window.location.pathname.replace(/\/+$/, "");
  const route = path.replace(/^\/react\/dashboard\/?/, "").split("/")[0] || "overview";
  if (route in MODULE_KEY_BY_ROUTE) return MODULE_KEY_BY_ROUTE[route];
  if (route === "deps") return "deps";
  if (route === "setup") return "setup";
  return "overview";
}

function dashboardPath(tab: TabKey = "overview") {
  return `/react/dashboard/${MODULE_BY_KEY[tab].route}`;
}

function authLoginHref() {
  const currentPath = `${window.location.pathname}${window.location.search}`;
  const next = currentPath.startsWith("/react/dashboard") ? currentPath : dashboardPath("overview");
  return `/api/auth/login?next=${encodeURIComponent(next)}`;
}

function Kpi({ label, value, hint }: Readonly<{ label: string; value: unknown; hint: string }>) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{formatNumber(value)}</CardTitle>
        <p className="text-xs text-zinc-500">{hint}</p>
      </CardHeader>
    </Card>
  );
}

function EmptyState({ title, message }: Readonly<{ title: string; message: string }>) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center">
      <Clock3 className="mx-auto mb-3 size-8 text-zinc-400" />
      <h3 className="text-base font-semibold text-zinc-950">{title}</h3>
      <p className="mx-auto mt-1 max-w-xl text-sm leading-6 text-zinc-600">{message}</p>
    </div>
  );
}

function SummaryRow({ label, value }: Readonly<{ label: string; value: unknown }>) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-zinc-100 py-2 last:border-0">
      <span className="text-sm text-zinc-600">{label}</span>
      <strong className="text-right text-sm font-semibold text-zinc-900">{String(value ?? "-")}</strong>
    </div>
  );
}

function asArray(value: unknown): any[] {
  return Array.isArray(value) ? value : [];
}

function isRecord(value: unknown): value is Record<string, any> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function formatListValue(value: unknown) {
  if (isRecord(value)) {
    return [value.priority, value.title, value.name, value.detail, value.message].filter(Boolean).join(": ");
  }
  return String(value ?? "");
}

function compactNumber(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0";
  if (Math.abs(number) >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}m`;
  if (Math.abs(number) >= 1_000) return `${(number / 1_000).toFixed(1)}k`;
  return formatNumber(number);
}

function barToneClass(tone: "success" | "warning" | "error" | "info" | "neutral" = "info") {
  if (tone === "success") return "bg-emerald-600";
  if (tone === "warning") return "bg-amber-500";
  if (tone === "error") return "bg-rose-600";
  if (tone === "neutral") return "bg-zinc-500";
  return "bg-blue-600";
}

function MetricBar({
  label,
  value,
  max,
  tone = "info",
}: Readonly<{ label: string; value: unknown; max: number; tone?: "success" | "warning" | "error" | "info" | "neutral" }>) {
  const numericValue = Number(value || 0);
  const pct = max > 0 ? Math.max(numericValue > 0 ? 5 : 0, Math.min(100, Math.round((numericValue / max) * 100))) : 0;
  return (
    <div className="grid grid-cols-[minmax(120px,1fr)_minmax(120px,2fr)_70px] items-center gap-3 text-sm">
      <span className="truncate text-zinc-700" title={label}>{label}</span>
      <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
        <div className={`h-full rounded-full ${barToneClass(tone)}`} style={{ width: `${pct}%` }} />
      </div>
      <strong className="text-right font-mono text-xs text-zinc-900">{formatNumber(numericValue)}</strong>
    </div>
  );
}

function ModulePageHeader({
  module,
  repo,
}: Readonly<{ module: ModuleConfig; repo: string }>) {
  const Icon = module.icon;
  return (
    <div className="mb-5">
      <SharedPageHeader
        eyebrow={module.eyebrow}
        title={module.title}
        description={module.description}
        repo={repo}
        meta={(
          <Pill className="border-zinc-200 bg-white font-mono text-zinc-700">
            <Icon className="size-3.5" />
            /dashboard/{module.route}
          </Pill>
        )}
        footer={(
          <p className="max-w-4xl border-l-2 border-zinc-200 pl-3 text-sm leading-6 text-zinc-600">
            <span className="font-semibold text-zinc-900">Page responsibility:</span> {module.responsibility}
          </p>
        )}
      />
    </div>
  );
}

function ModuleRouteStrip({
  activeTab,
  onSelect,
}: Readonly<{ activeTab: TabKey; onSelect: (tab: TabKey) => void }>) {
  return (
    <nav className="mb-5 overflow-x-auto rounded-lg border border-zinc-200 bg-white p-2" aria-label="Repository intelligence modules">
      <div className="flex min-w-max items-center gap-1">
        {MODULES.map((module) => {
          const Icon = module.icon;
          const active = activeTab === module.key;
          return (
            <button
              key={module.key}
              type="button"
              onClick={() => onSelect(module.key)}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-zinc-900 text-white" : "text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950",
              )}
            >
              <Icon className="size-4" />
              {module.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function MiniList({ title, values }: Readonly<{ title: string; values: unknown }>) {
  const list = asArray(values).filter(Boolean);
  if (!list.length) return null;
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-zinc-800">{title}</p>
      <div className="flex flex-wrap gap-2">
        {list.slice(0, 12).map((value, index) => (
          <Pill key={`${title}-${index}`} themed>{formatListValue(value)}</Pill>
        ))}
      </div>
    </div>
  );
}

function buildCodeflowUrl(repo?: string | null) {
  const params = new URLSearchParams();
  if (repo) params.set("repo", repo);
  params.set("auth", "server");
  const isLocalReactDevServer = ["5173", "5174"].includes(window.location.port);
  const codeflowBaseUrl = isLocalReactDevServer
    ? "/react/static/codeflow/index.html"
    : "/static/codeflow/index.html";
  return `${codeflowBaseUrl}?${params.toString()}`;
}

function CodeFlowWorkspace({ repo }: Readonly<{ repo: string }>) {
  const [reloadNonce, setReloadNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const baseUrl = buildCodeflowUrl(repo);
  const frameSrc = reloadNonce ? `${baseUrl}&reload=${reloadNonce}` : baseUrl;

  function reloadFrame() {
    setLoading(true);
    setReloadNonce(Date.now());
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardDescription className="font-semibold uppercase tracking-wide text-blue-600">Architecture map</CardDescription>
            <CardTitle>CodeFlow workspace</CardTitle>
            <p className="mt-1 text-sm text-zinc-600">
              Loaded for <span className="font-mono text-zinc-900">{repo || "No repo selected"}</span>
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={reloadFrame}>
              <RefreshCcw className="mr-2 size-4" />
              Reload Map
            </Button>
            <Button asChild variant="outline" size="sm">
              <a href={baseUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="mr-2 size-4" />
                Open Full Screen
              </a>
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="relative mx-auto h-[min(82vh,900px)] min-h-[760px] w-full max-w-[960px] overflow-hidden rounded-2xl border border-zinc-300 bg-[#050816] shadow-sm">
          {loading ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center gap-4 bg-[#050816]/90 text-zinc-300">
              <Loader2 className="size-8 animate-spin text-blue-400" />
              <div>
                <strong className="block text-sm font-semibold text-white">Loading CodeFlow architecture map</strong>
                <span className="text-xs text-zinc-400">Explorer, Canvas, and Insights are provided inside the embedded workspace.</span>
              </div>
            </div>
          ) : null}
          <iframe
            className="block size-full border-0 bg-[#050816]"
            title="CodeFlow Architecture Map"
            loading="lazy"
            referrerPolicy="no-referrer"
            src={frameSrc}
            onLoad={() => setLoading(false)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function safeReadmeUrl(value: string) {
  const url = value.trim();
  if (/^(https?:|mailto:)/i.test(url) || url.startsWith("#") || url.startsWith("/")) return url;
  return "#";
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenPattern =
    /(\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)|!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*)/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const key = `${keyPrefix}-${match.index}`;
    const token = match[0];

    if (token.startsWith("[![")) {
      nodes.push(
        <a key={key} href={safeReadmeUrl(match[4])} target="_blank" rel="noreferrer" className="inline-flex align-middle">
          <img src={safeReadmeUrl(match[3])} alt={match[2] || ""} className="inline-block max-h-7 max-w-full align-middle" />
        </a>,
      );
    } else if (token.startsWith("![")) {
      nodes.push(
        <img key={key} src={safeReadmeUrl(match[6])} alt={match[5] || ""} className="inline-block max-h-10 max-w-full align-middle" />,
      );
    } else if (token.startsWith("[")) {
      nodes.push(
        <a key={key} href={safeReadmeUrl(match[8])} target="_blank" rel="noreferrer" className="font-medium text-blue-600 hover:underline">
          {match[7]}
        </a>,
      );
    } else if (token.startsWith("`")) {
      nodes.push(
        <code key={key} className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[0.9em] text-zinc-900">
          {match[9]}
        </code>,
      );
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{match[10]}</strong>);
    }

    cursor = match.index + token.length;
  }

  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function ReadmePreview({ markdown }: Readonly<{ markdown: string }>) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const nodes: ReactNode[] = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let orderedList = false;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) {
      nodes.push(
        <p key={`p-${nodes.length}`} className="text-sm leading-7 text-zinc-700">
          {renderInlineMarkdown(text, `p-${nodes.length}`)}
        </p>,
      );
    }
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    const ListTag = orderedList ? "ol" : "ul";
    nodes.push(
      <ListTag key={`list-${nodes.length}`} className={cn("space-y-1 pl-6 text-sm leading-7 text-zinc-700", orderedList ? "list-decimal" : "list-disc")}>
        {listItems.map((item, index) => (
          <li key={`${item}-${index}`}>{renderInlineMarkdown(item, `li-${nodes.length}-${index}`)}</li>
        ))}
      </ListTag>,
    );
    listItems = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    const fenceMatch = trimmed.match(/^```(\w+)?/);
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)/);
    const unorderedMatch = trimmed.match(/^[-*]\s+(.+)/);
    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)/);
    const quoteMatch = trimmed.match(/^>\s+(.+)/);

    if (fenceMatch) {
      flushParagraph();
      flushList();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      nodes.push(
        <pre key={`code-${nodes.length}`} className="overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs leading-5 text-zinc-800">
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      flushParagraph();
      flushList();
      nodes.push(<hr key={`hr-${nodes.length}`} className="border-zinc-200" />);
      continue;
    }

    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      const HeadingTag = `h${Math.min(level + 1, 6)}` as keyof JSX.IntrinsicElements;
      nodes.push(
        <HeadingTag
          key={`h-${nodes.length}`}
          className={cn(
            "font-semibold tracking-normal text-zinc-950",
            level === 1 && "border-b border-zinc-200 pb-2 text-2xl",
            level === 2 && "text-xl",
            level > 2 && "text-base",
          )}
        >
          {renderInlineMarkdown(headingMatch[2], `h-${nodes.length}`)}
        </HeadingTag>,
      );
      continue;
    }

    if (unorderedMatch || orderedMatch) {
      flushParagraph();
      const nextOrdered = Boolean(orderedMatch);
      if (listItems.length && orderedList !== nextOrdered) flushList();
      orderedList = nextOrdered;
      listItems.push((orderedMatch || unorderedMatch)?.[1] || "");
      continue;
    }

    if (quoteMatch) {
      flushParagraph();
      flushList();
      nodes.push(
        <blockquote key={`quote-${nodes.length}`} className="border-l-4 border-zinc-200 pl-4 text-sm leading-7 text-zinc-600">
          {renderInlineMarkdown(quoteMatch[1], `quote-${nodes.length}`)}
        </blockquote>,
      );
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();

  return (
    <div className="max-h-[620px] overflow-y-auto overflow-x-hidden rounded-lg border border-zinc-200 bg-white p-6">
      <div className="space-y-4 break-words [overflow-wrap:anywhere]">{nodes}</div>
    </div>
  );
}

function splitCommitMessage(value: unknown) {
  const lines = String(value || "Commit")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return {
    title: lines[0] || "Commit",
    body: lines.slice(1).join(" "),
  };
}

function OverviewPanel({
  data,
  onOpenModule,
}: Readonly<{ data: AnalysisPayload | null; onOpenModule: (tab: TabKey) => void }>) {
  if (!data) {
    return (
      <SharedEmptyState
        title="Run a repository analysis"
        message="Overview will show repository metadata, contributors, activity, README coverage, and database-backed history after /api/analyze/full finishes."
      />
    );
  }

  const repoInfo = getRepoInfo(data);
  const metadata = data.metadata || {};
  const details = data.metadata_details || {};
  const contributors = Array.isArray(details.contributors) ? details.contributors : [];
  const commits = Array.isArray(details.commits) ? details.commits : [];
  const files = Array.isArray(details.file_trees) ? details.file_trees : [];
  const readme = String(details.repository?.readme || "").trim();
  const topics = normalizeTopics(repoInfo.topics).length ? normalizeTopics(repoInfo.topics) : normalizeTopics(data.topics);
  const cicd = data.cicd || {};
  const deps = getDependencies(data);
  const alerts = getAlerts(data);
  const depHealth = getHealth(data);
  const depScore = Number(depHealth.score ?? data.health_score ?? 0);
  const cicdFindings = collectCicdFindings(cicd);
  const detected = cicd.detected || cicd.detected_platforms || {};
  const workflows = Array.isArray(cicd.workflows) ? cicd.workflows : Array.isArray(cicd.analyses) ? cicd.analyses : [];
  const pipelineFileCount = Object.values(detected).reduce((sum: number, value) => sum + getPipelineFiles(value).length, 0) || workflows.length;
  const maxContributorCommits = Math.max(1, ...contributors.map((item: any) => Number(item.total_commits ?? item.contributions ?? 0)));
  const license = repoInfo.license?.spdx_id || repoInfo.license?.name || data.license_name || "N/A";
  const defaultBranch = repoInfo.default_branch || data.default_branch || "N/A";
  const homepage = repoInfo.homepage || repoInfo.html_url || repoInfo.url || "";
  const unpinned = deps.filter((dep: any) => !depVersion(dep) || depVersion(dep) === "*" || dep.pinning_type === "unpinned").length;
  const fileTypes = files.reduce<Record<string, number>>((acc: Record<string, number>, file: any) => {
    const type = String(file.file_type || file.type || "blob").toLowerCase();
    acc[type] = (acc[type] || 0) + 1;
    return acc;
  }, {});
  const topDirectories = files.reduce<Record<string, number>>((acc: Record<string, number>, file: any) => {
    const path = String(file.file_path || file.path || "");
    const root = path.includes("/") ? path.split("/")[0] : path ? "(root)" : "unknown";
    acc[root] = (acc[root] || 0) + 1;
    return acc;
  }, {});
  const topFileTypes = Object.entries(fileTypes).sort(([, a], [, b]) => b - a).slice(0, 6);
  const topDirectoryRows = Object.entries(topDirectories).sort(([, a], [, b]) => b - a).slice(0, 8);
  const attentionItems = [
    alerts.length
      ? { tone: "error" as const, title: "Dependency alerts", message: `${alerts.length} Dependabot alert${alerts.length === 1 ? "" : "s"} returned.` }
      : null,
    cicdFindings.length
      ? { tone: "warning" as const, title: "CI/CD findings", message: `${cicdFindings.length} workflow finding${cicdFindings.length === 1 ? "" : "s"} need review.` }
      : null,
    unpinned
      ? { tone: "warning" as const, title: "Unpinned dependencies", message: `${unpinned} package${unpinned === 1 ? "" : "s"} are unpinned or missing constraints.` }
      : null,
    !pipelineFileCount
      ? { tone: "warning" as const, title: "No workflow files", message: "No CI/CD workflow files were detected by the analyzer." }
      : null,
    !readme || readme === "No README file found."
      ? { tone: "info" as const, title: "README missing", message: "Repository documentation was not returned in this analysis." }
      : null,
  ].filter(Boolean) as Array<{ tone: "success" | "warning" | "error" | "info"; title: string; message: string }>;
  const overallTone = attentionItems.some((item) => item.tone === "error")
    ? "error"
    : attentionItems.some((item) => item.tone === "warning")
      ? "warning"
      : "success";
  const moduleLinks: Array<{ tab: TabKey; title: string; description: string; metric: string; tone: "success" | "warning" | "error" | "info" | "neutral" }> = [
    { tab: "cicd", title: "CI/CD", description: "Inspect workflows, jobs, checks, and automation risk.", metric: `${formatNumber(pipelineFileCount)} files`, tone: cicdFindings.length ? "warning" : "success" },
    { tab: "deps", title: "Dependencies", description: "Search package inventory, alerts, and ecosystem health.", metric: `${formatNumber(deps.length)} packages`, tone: alerts.length ? "error" : scoreTone(depScore) },
    { tab: "pipeline", title: "Pipeline Monitor", description: "Review GitHub Actions quality-gate enforcement runs.", metric: "runs", tone: "info" },
    { tab: "setup", title: "Repo Setup", description: "Configure workflow, secrets, and protected branch rules.", metric: "setup", tone: "neutral" },
  ];

  return (
    <div className="space-y-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
        <Card>
          <CardHeader>
            <SharedSectionHeader
              eyebrow="Repository identity"
              title={repoInfo.full_name || data.repo || "Repository"}
              description={repoInfo.description || "Repository metadata returned by the analyzer."}
              action={homepage ? (
                <Button asChild variant="outline" size="sm">
                  <a href={homepage} target="_blank" rel="noreferrer">
                    <ExternalLink className="mr-2 size-4" />
                    Open GitHub
                  </a>
                </Button>
              ) : null}
            />
          </CardHeader>
          <CardContent>
            <SummaryRow label="Language" value={repoInfo.language || metadata.language || "Unknown"} />
            <SummaryRow label="Default branch" value={defaultBranch} />
            <SummaryRow label="License" value={license} />
            <SummaryRow label="Open issues" value={formatNumber(repoInfo.open_issues_count ?? data.open_issues)} />
            <SummaryRow label="Archived" value={(repoInfo.is_archived ?? repoInfo.archived) ? "Yes" : "No"} />
            <SummaryRow label="Last pushed" value={formatDate(repoInfo.pushed_at || repoInfo.updated_at)} />
            <SummaryRow label="Analysis duration" value={`${formatNumber(data.analysis_duration_ms)} ms`} />
            <div className="mt-4 flex flex-wrap gap-2">
              {topics.length ? (
                topics.slice(0, 10).map((topic: string) => (
                  <Pill key={topic} themed>{topic}</Pill>
                ))
              ) : (
                <Pill themed>No topics loaded</Pill>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SharedSectionHeader
              eyebrow="Health snapshot"
              title="What needs attention?"
              description="High-signal findings routed to deeper module pages."
              action={<SharedStatusPill tone={overallTone} label={attentionItems.length ? "Review needed" : "Healthy"} />}
            />
          </CardHeader>
          <CardContent className="space-y-3">
            {attentionItems.length ? attentionItems.map((item) => (
              <div key={item.title} className="rounded-lg border border-zinc-200 p-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-zinc-950">{item.title}</h3>
                  <SharedStatusPill tone={item.tone} label={humanize(item.tone)} />
                </div>
                <p className="mt-2 text-sm leading-6 text-zinc-600">{item.message}</p>
              </div>
            )) : (
              <SharedEmptyState title="No immediate attention items" message="The analyzer did not return dependency alerts, CI/CD findings, or missing core metadata." icon={Check} />
            )}
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SharedMetricCard label="Stars" value={formatNumber(repoInfo.stars ?? repoInfo.stargazers_count ?? data.stars)} hint="GitHub popularity" icon={Github} tone="info" />
        <SharedMetricCard label="Forks" value={formatNumber(repoInfo.forks ?? repoInfo.forks_count ?? data.forks)} hint="Community copies" icon={BarChart3} tone="neutral" />
        <SharedMetricCard label="Commits" value={formatNumber(metadata.total_commits ?? commits.length)} hint="Total or sampled activity" icon={History} tone="info" />
        <SharedMetricCard label="Contributors" value={formatNumber(metadata.total_contributors ?? contributors.length)} hint="Loaded contributors" icon={User} tone="success" />
      </div>

      <section className="grid items-start gap-5 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <Card className="flex h-full flex-col">
          <CardHeader>
            <SharedSectionHeader title="Top contributors" description="Ranked by contribution count from repository metadata." />
          </CardHeader>
          <CardContent className="flex-1 space-y-3 overflow-y-auto overflow-x-hidden">
            {contributors.length ? (
              <>
                <div className="space-y-2">
                  {contributors.slice(0, 8).map((item: any) => (
                    <MetricBar
                      key={`bar-${item.username || item.login}`}
                      label={item.username || item.login || "unknown"}
                      value={item.total_commits ?? item.contributions ?? 0}
                      max={maxContributorCommits}
                    />
                  ))}
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  {contributors.slice(0, 8).map((item: any) => (
                    <div key={item.username || item.login} className="flex items-center justify-between rounded-md border border-zinc-200 px-3 py-2">
                      <div className="flex min-w-0 items-center gap-3">
                        {item.avatar_url ? <img src={item.avatar_url} alt="" className="size-8 rounded-full" /> : <div className="grid size-8 shrink-0 place-items-center rounded-full bg-zinc-100 text-xs font-semibold">{String(item.username || "U").slice(0, 2).toUpperCase()}</div>}
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold">{item.username || item.login || "unknown"}</div>
                          <div className="text-xs text-zinc-500">{formatNumber(item.total_commits ?? item.contributions)} commits</div>
                        </div>
                      </div>
                      <Pill themed>{compactNumber(item.total_commits ?? item.contributions ?? 0)}</Pill>
                    </div>
                  ))}
                </div>
              </>
            ) : <p className="text-sm text-zinc-600">No contributor detail returned yet.</p>}
          </CardContent>
        </Card>

        <Card className="flex h-full flex-col">
          <CardHeader>
            <SharedSectionHeader title="Recent commits" description="Recent activity with message previews and author context." />
          </CardHeader>
          <CardContent className="max-h-[560px] flex-1 space-y-3 overflow-y-auto overflow-x-hidden">
            {commits.length ? commits.slice(0, 12).map((commit: any, index: number) => {
              const message = splitCommitMessage(commit.message);
              return (
                <div key={`${commit.commit_hash || commit.sha || index}`} className="rounded-md border border-zinc-200 p-3">
                  <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
                    <span className="shrink-0 font-mono">{String(commit.commit_hash || commit.sha || "commit").slice(0, 8)}</span>
                    <span className="shrink-0 text-right">{formatDate(commit.timestamp || commit.date)}</span>
                  </div>
                  <p className="mt-2 break-words text-sm font-semibold leading-6 text-zinc-900 [overflow-wrap:anywhere]">{message.title}</p>
                  {message.body ? (
                    <p
                      className="mt-1 break-words text-xs leading-5 text-zinc-600 [overflow-wrap:anywhere]"
                      style={{ display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}
                    >
                      {message.body}
                    </p>
                  ) : null}
                  <p className="mt-2 text-xs text-zinc-500">{commit.author_name || commit.author || "Unknown"}</p>
                </div>
              );
            }) : <SharedEmptyState title="No commits returned" message="The metadata module did not return commit samples for this run." />}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>File structure summary</CardTitle>
              <CardDescription>Compact structure overview. Use deeper tooling for full architecture inspection.</CardDescription>
            </div>
            <Pill themed>{formatNumber(files.length)} entries</Pill>
          </div>
        </CardHeader>
        <CardContent className="grid gap-5 lg:grid-cols-2">
          {files.length ? (
            <>
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-zinc-950">File types</h3>
                {topFileTypes.map(([type, count]) => (
                  <MetricBar key={type} label={humanize(type)} value={count} max={files.length} tone={type === "tree" ? "neutral" : "info"} />
                ))}
              </div>
              <SharedDataTable
                rows={topDirectoryRows}
                getRowKey={(row) => String(row[0])}
                columns={[
                  { key: "directory", header: "Directory", render: (row) => <span className="font-mono text-xs">{row[0]}</span> },
                  { key: "files", header: "Entries", render: (row) => formatNumber(row[1]) },
                ]}
                empty="No directory summary returned."
              />
            </>
          ) : (
            <SharedEmptyState title="No file tree returned" message="The metadata module did not return repository structure data for this run." />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader title="README preview" description="Rendered README content captured during metadata extraction." />
        </CardHeader>
        <CardContent>
          {readme && readme !== "No README file found." ? (
            <ReadmePreview markdown={readme} />
          ) : (
            <p className="rounded-md border border-dashed border-zinc-300 p-5 text-sm text-zinc-600">No README file found.</p>
          )}
        </CardContent>
      </Card>

      <section>
        <SharedSectionHeader
          eyebrow="Next steps"
          title="Jump into deeper modules"
          description="Overview stays high-level; detailed investigation lives in the dedicated module pages."
        />
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {moduleLinks.map((item) => (
            <button
              key={item.tab}
              className="rounded-lg border border-zinc-200 bg-white p-4 text-left transition-colors hover:border-blue-200 hover:bg-blue-50/40"
              onClick={() => onOpenModule(item.tab)}
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold text-zinc-950">{item.title}</h3>
                <SharedStatusPill tone={item.tone} label={item.metric} />
              </div>
              <p className="mt-3 text-sm leading-6 text-zinc-600">{item.description}</p>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function collectCicdFindings(cicd: Record<string, any>) {
  const findings: any[] = [];
  for (const securityResult of asArray(cicd.security_results)) {
    const failed = [...asArray(securityResult.findings), ...asArray(securityResult.failed_checks)];
    for (const item of failed) {
      findings.push({ ...item, file: securityResult.file, score: securityResult.score });
    }
    if (securityResult.issues_found && !failed.length) {
      findings.push({
        title: `${securityResult.issues_found} issues`,
        severity: "medium",
        file: securityResult.file,
        score: securityResult.score,
      });
    }
  }
  return findings;
}

function collectPassedChecks(cicd: Record<string, any>) {
  const checks: any[] = [];
  for (const securityResult of asArray(cicd.security_results)) {
    for (const item of [...asArray(securityResult.passed), ...asArray(securityResult.passed_checks)]) {
      checks.push({ ...item, file: securityResult.file });
    }
  }
  return checks;
}

function severityCounts(findings: any[]) {
  return findings.reduce<Record<string, number>>((acc, item) => {
    const key = String(item.severity || item.level || "medium").toLowerCase();
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function securityScoreAverage(securityResults: any[]) {
  if (!securityResults.length) return null;
  const total = securityResults.reduce((sum, item) => sum + Number(item.score || 0), 0);
  return Math.round(total / securityResults.length);
}

function severityTone(severity?: string | null): "success" | "warning" | "error" | "info" {
  const value = String(severity || "").toLowerCase();
  if (value.includes("high") || value.includes("critical")) return "error";
  if (value.includes("medium") || value.includes("moderate")) return "warning";
  if (value.includes("low")) return "info";
  return "info";
}

function getPipelineFiles(files: unknown) {
  if (Array.isArray(files)) return files;
  if (isRecord(files) && Array.isArray(files.files)) return files.files;
  return [];
}

function PipelineFilesCard({ platform, files }: Readonly<{ platform: string; files: unknown }>) {
  const fileList = getPipelineFiles(files);
  return (
    <div className="rounded-lg border border-zinc-200 p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold capitalize">{platform.replace(/_/g, " ")}</h3>
        <Pill themed>{fileList.length} files</Pill>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {fileList.length ? fileList.map((file, index) => (
          <Pill key={`${platform}-${index}`} themed className="font-mono">{String(file)}</Pill>
        )) : <p className="text-sm text-zinc-600">No file list returned for this platform.</p>}
      </div>
    </div>
  );
}

function JobsTable({ jobs }: Readonly<{ jobs: any[] }>) {
  if (!jobs.length) return <p className="text-sm text-zinc-600">No job detail parsed.</p>;
  return (
    <div className="overflow-x-auto rounded-md border border-zinc-200">
      <table className="w-full min-w-[680px] text-left text-xs">
        <thead className="border-b border-zinc-200 bg-zinc-50 uppercase tracking-wide text-zinc-600">
          <tr>
            <th className="px-3 py-2">Job</th>
            <th className="px-3 py-2">Runner / Stage</th>
            <th className="px-3 py-2">Needs</th>
            <th className="px-3 py-2">Steps</th>
          </tr>
        </thead>
        <tbody>
          {jobs.slice(0, 16).map((job, index) => (
            <tr key={`${job.id || job.name || index}`} className="border-b border-zinc-100 last:border-0">
              <td className="px-3 py-2 font-mono font-semibold">{job.name || job.id || "job"}</td>
              <td className="px-3 py-2">{job.runner || job.stage || job.image || "N/A"}</td>
              <td className="px-3 py-2">{Array.isArray(job.needs) ? job.needs.join(", ") : job.needs || "None"}</td>
              <td className="px-3 py-2">{Array.isArray(job.steps) ? job.steps.map((step: any) => step.name || step.run || step.uses || "step").slice(0, 8).join(", ") : "N/A"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PipelineAnalysisCard({ item }: Readonly<{ item: any }>) {
  const jobs = asArray(item.jobs);
  const stages = asArray(item.stages);
  const triggers = asArray(item.triggers);
  const envVars = asArray(item.env_vars);
  const artifacts = asArray(item.artifacts);
  const services = asArray(item.services);
  const estimatedMinutes = item.estimated_minutes ?? item.estimated_duration_minutes;
  const features = [
    ["Caching", item.caching],
    ["Matrix", item.matrix_builds],
    ["Manual approval", item.manual_approval],
    ["Notifications", item.notifications],
    ["Security scanning", item.security_scanning],
  ];

  return (
    <div className="space-y-4 rounded-lg border border-zinc-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">{item.platform || "Pipeline"}</p>
          <h3 className="mt-1 font-mono text-sm font-semibold text-zinc-950">{item.file || item.path || item.name || "pipeline"}</h3>
        </div>
        <Pill themed>{formatNumber(item.line_count || 0)} lines</Pill>
      </div>
      <div className="flex flex-wrap gap-2">
        <Pill themed>{jobs.length} jobs</Pill>
        <Pill themed>{stages.length} stages</Pill>
        <Pill themed>{triggers.length} triggers</Pill>
        <Pill themed>{envVars.length} env vars</Pill>
        <Pill themed>{artifacts.length} artifacts</Pill>
        <Pill themed>{services.length} services</Pill>
        {item.pipeline_type ? <Pill themed>{item.pipeline_type}</Pill> : null}
        {item.complexity_score != null ? <Pill themed>complexity {item.complexity_score}</Pill> : null}
        {estimatedMinutes != null ? <Pill themed>{estimatedMinutes} min est.</Pill> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {features.map(([label, active]) => (
          <Pill key={String(label)} themed>
            <PillIndicator variant={active ? "success" : "info"} />
            {label}: {active ? "yes" : "no"}
          </Pill>
        ))}
      </div>
      {triggers.length ? <p className="text-sm text-zinc-600"><strong>Triggers:</strong> {triggers.join(", ")}</p> : null}
      <MiniList title="Stages" values={stages} />
      <MiniList title="Environment variables" values={envVars} />
      <MiniList title="Artifacts" values={artifacts} />
      <MiniList title="Services" values={services} />
      <JobsTable jobs={jobs} />
      <MiniList title="Best practices" values={item.best_practices} />
      <MiniList title="Recommendations" values={item.recommendations} />
    </div>
  );
}

function FindingCard({ item }: Readonly<{ item: any }>) {
  const severity = String(item.severity || item.level || "medium").toUpperCase();
  const lines = asArray(item.matched_lines);
  return (
    <div className="rounded-lg border border-zinc-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold text-zinc-950">{item.name || item.title || item.rule || "Security finding"}</h4>
          <p className="mt-1 font-mono text-xs text-zinc-500">{item.rule_id || item.file || ""}</p>
        </div>
        <Pill themed>
          <PillIndicator variant={severityTone(severity)} />
          {severity}
        </Pill>
      </div>
      <p className="mt-3 text-sm text-zinc-600">{item.description || item.message || "Review this pipeline finding."}</p>
      {item.remediation ? <p className="mt-2 text-sm text-zinc-800"><strong>Fix:</strong> {item.remediation}</p> : null}
      {lines.length ? (
        <pre className="mt-3 max-h-52 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs leading-5">
          {lines.map((line: any) => `${line.line_num || ""}: ${line.content || ""}`).join("\n")}
        </pre>
      ) : null}
    </div>
  );
}

function CategoryCoverage({ securityResults }: Readonly<{ securityResults: any[] }>) {
  const totals: Record<string, { passed: number; failed: number }> = {};
  for (const result of securityResults) {
    for (const [category, value] of Object.entries(result.categories || {})) {
      const entry = isRecord(value) ? value : {};
      totals[category] ||= { passed: 0, failed: 0 };
      totals[category].passed += Number(entry.passed || 0);
      totals[category].failed += Number(entry.failed || 0);
    }
  }
  const entries = Object.entries(totals);
  if (!entries.length) return <p className="text-sm text-zinc-600">No category data returned.</p>;
  return (
    <div className="space-y-3">
      {entries.map(([category, value]) => (
        <MetricBar
          key={category}
          label={category}
          value={value.failed}
          max={Math.max(1, value.passed + value.failed)}
          tone={value.failed ? "error" : "success"}
        />
      ))}
    </div>
  );
}

type CicdWorkflowRow = {
  id: string;
  platform: string;
  file: string;
  jobs: number;
  triggers: string[];
  score?: number | null;
  lineCount?: number | null;
  workflow?: any;
};

type CicdJobCheckRow = {
  id: string;
  type: "job" | "passed_check" | "failed_check";
  source: string;
  name: string;
  status: string;
  detail: string;
  raw: any;
};

function workflowFileName(value: unknown) {
  if (isRecord(value)) return String(value.file || value.path || value.name || value.workflow || "workflow");
  return String(value || "workflow");
}

function workflowName(value: any) {
  return String(value?.name || value?.workflow_name || value?.file || value?.path || "workflow");
}

function workflowSourceFile(value: any) {
  return String(value?.file || value?.path || value?.source || value?.name || "workflow");
}

function workflowPlatform(value: any, fallback = "unknown") {
  return String(value?.platform || value?.provider || value?.type || fallback || "unknown").replace(/_/g, " ");
}

function compactList(value: unknown, limit = 4) {
  const list = asArray(value).map(formatListValue).filter(Boolean);
  if (!list.length) return "N/A";
  const visible = list.slice(0, limit).join(", ");
  return list.length > limit ? `${visible}, +${list.length - limit}` : visible;
}

function buildWorkflowRows(platforms: string[], detected: Record<string, any>, workflows: any[]): CicdWorkflowRow[] {
  const rows: CicdWorkflowRow[] = [];
  const byFile = new Map<string, any>();
  workflows.forEach((workflow) => byFile.set(workflowSourceFile(workflow), workflow));

  for (const platform of platforms) {
    for (const file of getPipelineFiles(detected[platform])) {
      const fileName = workflowFileName(file);
      const workflow = byFile.get(fileName);
      rows.push({
        id: `${platform}:${fileName}`,
        platform,
        file: fileName,
        jobs: asArray(workflow?.jobs).length,
        triggers: asArray(workflow?.triggers),
        score: workflow?.security_score ?? workflow?.score ?? null,
        lineCount: workflow?.line_count ?? null,
        workflow,
      });
    }
  }

  workflows.forEach((workflow, index) => {
    const file = workflowSourceFile(workflow);
    if (rows.some((row) => row.file === file)) return;
    rows.push({
      id: `analysis:${file}:${index}`,
      platform: workflowPlatform(workflow),
      file,
      jobs: asArray(workflow.jobs).length,
      triggers: asArray(workflow.triggers),
      score: workflow.security_score ?? workflow.score ?? null,
      lineCount: workflow.line_count ?? null,
      workflow,
    });
  });

  return rows;
}

function buildJobCheckRows(workflows: any[], passedChecks: any[], findings: any[]): CicdJobCheckRow[] {
  const rows: CicdJobCheckRow[] = [];
  workflows.forEach((workflow, workflowIndex) => {
    asArray(workflow.jobs).forEach((job, jobIndex) => {
      rows.push({
        id: `job:${workflowIndex}:${jobIndex}`,
        type: "job",
        source: workflowSourceFile(workflow),
        name: String(job.name || job.id || `job ${jobIndex + 1}`),
        status: "defined",
        detail: [
          job.runner || job.stage || job.image,
          Array.isArray(job.steps) ? `${job.steps.length} steps` : null,
          Array.isArray(job.needs) && job.needs.length ? `needs ${job.needs.join(", ")}` : null,
        ].filter(Boolean).join(" · ") || "No job metadata",
        raw: job,
      });
    });
  });

  passedChecks.slice(0, 100).forEach((check, index) => {
    rows.push({
      id: `passed:${index}`,
      type: "passed_check",
      source: String(check.file || check.category || "security check"),
      name: String(check.name || check.title || "Passed check"),
      status: "passed",
      detail: String(check.category || check.description || check.message || "Security control passed."),
      raw: check,
    });
  });

  findings.slice(0, 100).forEach((finding, index) => {
    rows.push({
      id: `failed:${index}`,
      type: "failed_check",
      source: String(finding.file || finding.category || "security finding"),
      name: String(finding.name || finding.title || finding.rule || "Failed check"),
      status: String(finding.severity || finding.level || "failed"),
      detail: String(finding.description || finding.message || finding.remediation || "Review finding."),
      raw: finding,
    });
  });

  return rows;
}

function groupedFindings(findings: any[]) {
  const groups: Record<string, any[]> = {};
  findings.forEach((finding) => {
    const severity = String(finding.severity || finding.level || "unknown").toLowerCase();
    groups[severity] ||= [];
    groups[severity].push(finding);
  });
  const order = ["critical", "high", "medium", "moderate", "low", "info", "unknown"];
  return Object.entries(groups).sort(([left], [right]) => {
    const leftIndex = order.indexOf(left);
    const rightIndex = order.indexOf(right);
    return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
  });
}

function CicdPanel({ data }: Readonly<{ data: AnalysisPayload | null }>) {
  const [selectedWorkflow, setSelectedWorkflow] = useState<any | null>(null);
  if (!data) {
    return <SharedEmptyState title="No CI/CD analysis yet" message="Run an analysis to detect GitHub Actions, workflow health, jobs, triggers, and parser details." />;
  }
  const cicd = data.cicd || {};
  const detected = cicd.detected || cicd.detected_platforms || {};
  const platforms = Array.isArray(cicd.platforms)
    ? cicd.platforms
    : Object.keys(detected).filter((key) => Array.isArray(detected[key]) && detected[key].length);
  const analyses = Array.isArray(cicd.analyses) ? cicd.analyses : Array.isArray(cicd.pipeline_analyses) ? cicd.pipeline_analyses : [];
  const securityResults = asArray(cicd.security_results);
  const findings = collectCicdFindings(cicd);
  const passedChecks = collectPassedChecks(cicd);
  const counts = severityCounts(findings);
  const averageScore = securityScoreAverage(securityResults);
  const workflows = Array.isArray(cicd.workflows) ? cicd.workflows : analyses;
  const pipelineFileCount = Object.values(detected).reduce((sum: number, value) => sum + getPipelineFiles(value).length, 0) || analyses.length;
  const latestRun = cicd.latest_run || {};
  const severityMax = Math.max(1, counts.critical || 0, counts.high || 0, counts.medium || 0, counts.low || 0);
  const workflowRows = buildWorkflowRows(platforms, detected, workflows);
  const jobCheckRows = buildJobCheckRows(workflows, passedChecks, findings);
  const findingGroups = groupedFindings(findings);
  const healthTone = findings.length ? severityToTone(findings[0]?.severity || "warning") : "success";

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-zinc-200 bg-white p-5">
        <SharedSectionHeader
          eyebrow="CI/CD health summary"
          title="Pipeline health at a glance"
          description="Compact status for the analyzer output before diving into workflow files, jobs, and findings."
          action={<SharedStatusPill tone={healthTone} label={findings.length ? "Needs review" : "Healthy"} />}
        />
        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <SharedMetricCard label="Security score" value={averageScore ?? 0} hint={averageScore == null ? "No security checks" : "Average CI/CD score"} icon={ShieldCheck} tone={scoreTone(averageScore) as any} />
          <SharedMetricCard label="Platforms" value={platforms.length} hint="Detected CI/CD systems" icon={TerminalSquare} tone={platforms.length ? "info" : "neutral"} />
          <SharedMetricCard label="Pipeline files" value={pipelineFileCount} hint="Files scanned" icon={FileJson} tone={pipelineFileCount ? "success" : "neutral"} />
          <SharedMetricCard label="Findings" value={findings.length} hint="Failed security controls" icon={AlertTriangle} tone={findings.length ? "error" : "success"} />
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader>
            <SharedSectionHeader
              eyebrow="Severity"
              title="Finding distribution"
              description="Counts are grouped from security_results findings and failed checks."
            />
          </CardHeader>
          <CardContent className="space-y-3">
            {findings.length ? (
              <>
                <MetricBar label="Critical" value={counts.critical || 0} max={severityMax} tone="error" />
                <MetricBar label="High" value={counts.high || 0} max={severityMax} tone="error" />
                <MetricBar label="Medium" value={counts.medium || 0} max={severityMax} tone="warning" />
                <MetricBar label="Low" value={counts.low || 0} max={severityMax} tone="success" />
              </>
            ) : <p className="text-sm text-zinc-600">No severity findings to chart.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SharedSectionHeader
              eyebrow="Analyzer report"
              title="Report and latest run"
              description="HTML report and latest workflow-run summary, when returned by the backend."
              action={cicd.report_url ? (
                <Button asChild size="sm">
                  <a href={cicd.report_url} target="_blank" rel="noreferrer">
                    <ExternalLink className="mr-2 size-4" />
                    Open report
                  </a>
                </Button>
              ) : null}
            />
          </CardHeader>
          <CardContent>
            <div className="mt-4 flex flex-wrap gap-2">
              {platforms.length ? platforms.map((platform: string) => <Pill key={platform} themed>{platform}</Pill>) : <Pill themed>No platforms</Pill>}
            </div>
            <div className="mt-4">
              <SummaryRow label="Latest run" value={latestRun.name || latestRun.status || "N/A"} />
              <SummaryRow label="Conclusion" value={latestRun.conclusion || "N/A"} />
              <SummaryRow label="Run number" value={latestRun.run_number || "N/A"} />
              <SummaryRow label="Warnings" value={cicd.warning_count || asArray(cicd.warnings).length || 0} />
            </div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Workflow files"
            title="Detected workflow files"
            description="One row per detected workflow file, with parser details opened in a drawer."
            action={<SharedStatusPill tone="neutral" label={`${pipelineFileCount} files`} />}
          />
        </CardHeader>
        <CardContent>
          <SharedDataTable<CicdWorkflowRow>
            rows={workflowRows}
            getRowKey={(row) => row.id}
            empty="No workflow files returned by the analyzer."
            columns={[
              {
                key: "platform",
                header: "Platform",
                render: (row) => <SharedStatusPill tone="info" label={row.platform} />,
              },
              {
                key: "file",
                header: "Workflow file",
                render: (row) => <span className="font-mono text-xs text-zinc-950">{row.file}</span>,
              },
              {
                key: "jobs",
                header: "Jobs",
                render: (row) => row.jobs || "N/A",
              },
              {
                key: "triggers",
                header: "Triggers",
                render: (row) => compactList(row.triggers),
              },
              {
                key: "score",
                header: "Score",
                render: (row) => row.score == null ? "N/A" : <SharedStatusPill tone={scoreTone(Number(row.score)) as any} label={row.score} />,
              },
              {
                key: "details",
                header: "",
                render: (row) => row.workflow ? <DrawerButton onClick={() => setSelectedWorkflow(row.workflow)}>Details</DrawerButton> : <span className="text-xs text-zinc-500">Detected only</span>,
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Jobs and checks"
            title="Parsed jobs, passed controls, and failed controls"
            description="Jobs come from workflow parser output; checks come from security_results passed and failed checks."
            action={<SharedStatusPill tone="neutral" label={`${jobCheckRows.length} rows`} />}
          />
        </CardHeader>
        <CardContent>
          <SharedDataTable<CicdJobCheckRow>
            rows={jobCheckRows}
            getRowKey={(row) => row.id}
            empty="No job, passed-check, or failed-check detail returned."
            columns={[
              {
                key: "type",
                header: "Type",
                render: (row) => <SharedStatusPill tone={row.type === "failed_check" ? "error" : row.type === "passed_check" ? "success" : "neutral"} label={row.type.replace(/_/g, " ")} />,
              },
              {
                key: "source",
                header: "Source",
                render: (row) => <span className="font-mono text-xs text-zinc-700">{row.source}</span>,
              },
              {
                key: "name",
                header: "Name",
                render: (row) => <span className="font-semibold text-zinc-950">{row.name}</span>,
              },
              {
                key: "status",
                header: "Status",
                render: (row) => <SharedStatusPill tone={severityToTone(row.status)} label={row.status} />,
              },
              {
                key: "detail",
                header: "Detail",
                render: (row) => <span className="line-clamp-2 text-sm leading-6">{row.detail}</span>,
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Findings"
            title="Failures grouped by severity"
            description="Failed checks and findings are grouped so critical items do not get buried."
            action={<SharedStatusPill tone={findings.length ? "error" : "success"} label={findings.length ? "Review" : "Pass"} />}
          />
        </CardHeader>
        <CardContent className="space-y-5">
          {findingGroups.length ? findingGroups.map(([severity, items]) => (
            <section key={severity} className="space-y-3">
              <div className="flex items-center gap-2">
                <SharedStatusPill tone={severityToTone(severity)} label={`${severity.toUpperCase()} - ${items.length}`} />
              </div>
              <div className="grid gap-3 xl:grid-cols-2">
                {items.map((finding, index) => {
                  const lines = asArray(finding.matched_lines);
                  return (
                    <SharedFindingCard
                      key={`${finding.rule_id || finding.title || finding.name || index}`}
                      title={finding.name || finding.title || finding.rule || "Security finding"}
                      message={finding.description || finding.message || "Review this pipeline finding."}
                      severity={finding.severity || finding.level || severity}
                      file={finding.file}
                      ruleId={finding.rule_id || finding.rule}
                      recommendation={finding.remediation || finding.recommendation}
                      evidence={lines.length ? (
                        <pre className="max-h-48 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs leading-5">
                          {lines.map((line: any) => `${line.line_num || ""}: ${line.content || ""}`).join("\n")}
                        </pre>
                      ) : null}
                    />
                  );
                })}
              </div>
            </section>
          )) : <SharedEmptyState title="No failed CI/CD security checks" message="The analyzer did not return failed CI/CD findings for this repository." icon={ShieldCheck} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Coverage"
            title="Security category coverage"
            description="Passed and failed checks grouped by CI/CD security category."
          />
        </CardHeader>
        <CardContent>
          <CategoryCoverage securityResults={securityResults} />
        </CardContent>
      </Card>

      <SharedDetailDrawer
        open={Boolean(selectedWorkflow)}
        title={selectedWorkflow ? workflowName(selectedWorkflow) : "Workflow detail"}
        description={selectedWorkflow ? workflowSourceFile(selectedWorkflow) : undefined}
        onClose={() => setSelectedWorkflow(null)}
      >
        {selectedWorkflow ? (
          <div className="space-y-5">
            <Card>
              <CardHeader>
                <SharedSectionHeader title="Workflow summary" description="Parser output for the selected workflow file." />
              </CardHeader>
              <CardContent>
                <div className="grid gap-2">
                  <SummaryRow label="Platform" value={workflowPlatform(selectedWorkflow)} />
                  <SummaryRow label="Jobs" value={asArray(selectedWorkflow.jobs).length} />
                  <SummaryRow label="Stages" value={asArray(selectedWorkflow.stages).length} />
                  <SummaryRow label="Triggers" value={compactList(selectedWorkflow.triggers, 8)} />
                  <SummaryRow label="Line count" value={selectedWorkflow.line_count || "N/A"} />
                  <SummaryRow label="Complexity" value={selectedWorkflow.complexity_score || "N/A"} />
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <SharedSectionHeader title="Jobs" description="Jobs parsed from this workflow." />
              </CardHeader>
              <CardContent>
                <JobsTable jobs={asArray(selectedWorkflow.jobs)} />
              </CardContent>
            </Card>
            <MiniList title="Stages" values={selectedWorkflow.stages} />
            <MiniList title="Environment variables" values={selectedWorkflow.env_vars} />
            <MiniList title="Artifacts" values={selectedWorkflow.artifacts} />
            <MiniList title="Services" values={selectedWorkflow.services} />
            <MiniList title="Best practices" values={selectedWorkflow.best_practices} />
            <MiniList title="Recommendations" values={selectedWorkflow.recommendations} />
          </div>
        ) : null}
      </SharedDetailDrawer>
    </div>
  );
}

function depName(dep: any) {
  return dep.name || dep.package || dep.dependency || "unknown";
}

function depVersion(dep: any) {
  return dep.version_constraint || dep.version || dep.current_version || dep.constraint || "";
}

function alertPackage(alert: any) {
  return alert?.dependency?.package?.name || alert?.security_vulnerability?.package?.name || alert?.package?.name || alert?.package || alert?.name || "";
}

function countOutdated(deps: any[]) {
  return deps.filter((dep) => {
    const latest = dep.latest_version;
    const current = depVersion(dep);
    return dep.is_outdated === true || (latest && current && String(latest) !== String(current));
  }).length;
}

function depStatus(dep: any, alerts: any[]): ["VULNERABLE" | "OUTDATED" | "UNPINNED" | "PASS", "success" | "warning" | "error"] {
  const vulnerable = alerts.some((alert) => alertPackage(alert) === depName(dep));
  const latest = dep.latest_version;
  const current = depVersion(dep);
  const outdated = dep.is_outdated === true || (latest && current && String(latest) !== String(current));
  if (vulnerable) return ["VULNERABLE", "error"];
  if (outdated) return ["OUTDATED", "warning"];
  if (!current || current === "*" || dep.pinning_type === "unpinned") return ["UNPINNED", "warning"];
  return ["PASS", "success"];
}

function HealthBreakdown({ breakdown }: Readonly<{ breakdown: Record<string, any> }>) {
  const labels: Array<[string, string, number, "info" | "error"]> = [
    ["pinning_quality", "Pinning quality", 40, "info"],
    ["range_tightness", "Range tightness", 20, "info"],
    ["count_risk", "Dependency count", 15, "info"],
    ["outdated_flags", "Outdated flags", 15, "info"],
    ["completeness", "Manifest completeness", 10, "info"],
    ["cve_penalty", "CVE penalty", 30, "error"],
    ["license_penalty", "License penalty", 30, "error"],
    ["maintenance_penalty", "Maintenance penalty", 30, "error"],
  ];
  const rows = labels.filter(([key]) => breakdown[key] != null);
  if (!rows.length) return <p className="text-sm text-zinc-600">No score breakdown returned.</p>;
  return (
    <div className="space-y-3">
      {rows.map(([key, label, max, tone]) => (
        <MetricBar key={key} label={label} value={breakdown[key]} max={max} tone={tone} />
      ))}
    </div>
  );
}

function EcosystemCard({ name, info }: Readonly<{ name: string; info: Record<string, any> }>) {
  const manifests = asArray(info.manifest_files);
  const locks = asArray(info.lock_files);
  return (
    <div className="rounded-lg border border-zinc-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">{name}</p>
          <h3 className="mt-1 font-semibold">{name} ecosystem</h3>
        </div>
        <Pill themed>
          <PillIndicator variant={info.has_lock_file ? "success" : "warning"} />
          {info.has_lock_file ? "lockfile" : "no lockfile"}
        </Pill>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {manifests.length ? manifests.map((file, index) => <Pill key={`manifest-${index}`} themed className="font-mono">{String(file)}</Pill>) : <Pill themed>No manifest list</Pill>}
        {locks.map((file, index) => <Pill key={`lock-${index}`} themed className="font-mono"><PillIndicator variant="success" />{String(file)}</Pill>)}
      </div>
      {info.indicator_count != null ? <p className="mt-3 text-sm text-zinc-600">{formatNumber(info.indicator_count)} ecosystem indicators found.</p> : null}
    </div>
  );
}

function DependabotAlertCard({ alert }: Readonly<{ alert: any }>) {
  const pkg = alertPackage(alert) || "unknown package";
  const vulnerability = alert.security_vulnerability || {};
  const advisory = alert.security_advisory || {};
  const severity = String(vulnerability.severity || alert.severity || "unknown").toUpperCase();
  return (
    <div className="rounded-lg border border-zinc-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-mono font-semibold">{pkg}</h4>
          <p className="mt-1 text-sm text-zinc-600">{advisory.summary || vulnerability.vulnerable_version_range || alert.state || "Dependabot alert"}</p>
        </div>
        <Pill themed>
          <PillIndicator variant={severityTone(severity)} />
          {severity}
        </Pill>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {vulnerability.package?.ecosystem ? <Pill themed>{vulnerability.package.ecosystem}</Pill> : null}
        {vulnerability.vulnerable_version_range ? <Pill themed className="font-mono">{vulnerability.vulnerable_version_range}</Pill> : null}
        {vulnerability.first_patched_version?.identifier ? <Pill themed className="font-mono"><PillIndicator variant="success" />patched {vulnerability.first_patched_version.identifier}</Pill> : null}
      </div>
    </div>
  );
}

function ecosystemFromSource(value: unknown) {
  const source = String(value || "").toLowerCase();
  if (source.includes("package.json") || source.includes("package-lock") || source.includes("pnpm-lock") || source.includes("yarn.lock")) return "npm";
  if (source.includes("requirements") || source.includes("pyproject") || source.includes("poetry.lock") || source.includes("pipfile")) return "python";
  if (source.includes("pom.xml") || source.includes("build.gradle") || source.includes("gradle.lockfile")) return "java";
  if (source.includes("go.mod") || source.includes("go.sum")) return "go";
  if (source.includes("cargo.toml") || source.includes("cargo.lock")) return "rust";
  if (source.includes("gemfile")) return "ruby";
  if (source.includes("composer.json") || source.includes("composer.lock")) return "php";
  return "unknown";
}

function dependencyEcosystem(dep: any) {
  return String(
    dep.ecosystem ||
    dep.package_manager ||
    dep.manager ||
    dep.language ||
    ecosystemFromSource(dep.source_file || dep.file || dep.source),
  );
}

function dependencySource(dep: any) {
  return String(dep.source_file || dep.file || dep.manifest || dep.lock_file || dep.source || "N/A");
}

function dependencyScope(dep: any) {
  if (dep.is_dev === true || dep.scope === "dev" || dep.dependency_type === "development") return "dev";
  if (dep.scope) return String(dep.scope);
  return "prod";
}

function dependencyDepth(dep: any) {
  if (dep.is_transitive === true || dep.depth === "transitive" || dep.dependency_type === "transitive") return "transitive";
  return "direct";
}

function alertSeverity(alert: any) {
  return String(alert?.security_vulnerability?.severity || alert?.security_advisory?.severity || alert?.severity || "unknown").toLowerCase();
}

function alertEcosystem(alert: any) {
  return String(alert?.dependency?.package?.ecosystem || alert?.security_vulnerability?.package?.ecosystem || alert?.package?.ecosystem || "unknown");
}

function dependencyRows(deps: any[], alerts: any[]) {
  return deps.map((dep, index) => {
    const [status, tone] = depStatus(dep, alerts);
    return {
      id: `${depName(dep)}-${dependencySource(dep)}-${index}`,
      dep,
      name: depName(dep),
      version: depVersion(dep) || "N/A",
      pinning: String(dep.pinning_type || "unknown"),
      ecosystem: dependencyEcosystem(dep),
      source: dependencySource(dep),
      scope: dependencyScope(dep),
      depth: dependencyDepth(dep),
      license: String(dep.license || "unknown"),
      latest: String(dep.latest_version || "N/A"),
      status,
      tone,
      search: [
        depName(dep),
        depVersion(dep),
        dependencyEcosystem(dep),
        dependencySource(dep),
        dependencyScope(dep),
        dependencyDepth(dep),
        dep.license,
        dep.latest_version,
        status,
      ].join(" ").toLowerCase(),
    };
  });
}

function dependencyAlertRows(alerts: any[]) {
  return alerts.map((alert, index) => {
    const vulnerability = alert.security_vulnerability || {};
    const advisory = alert.security_advisory || {};
    return {
      id: `${alertPackage(alert) || "alert"}-${index}`,
      pkg: alertPackage(alert) || "unknown package",
      severity: alertSeverity(alert),
      ecosystem: alertEcosystem(alert),
      range: String(vulnerability.vulnerable_version_range || alert.vulnerable_version_range || "N/A"),
      patched: String(vulnerability.first_patched_version?.identifier || alert.first_patched_version || "N/A"),
      state: String(alert.state || "open"),
      summary: String(advisory.summary || alert.summary || "Dependabot alert"),
    };
  });
}

function DependenciesPanel({ data }: Readonly<{ data: AnalysisPayload | null }>) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [ecosystemFilter, setEcosystemFilter] = useState("all");
  const [scopeFilter, setScopeFilter] = useState("all");

  if (!data) {
    return <SharedEmptyState title="No dependency analysis yet" message="Run an analysis to inspect package health, vulnerabilities, outdated packages, and dependency risk." />;
  }
  const depsData = data.dependencies || {};
  const deps = getDependencies(data);
  const alerts = getAlerts(data);
  const health = getHealth(data);
  const score = Number(health.score ?? data.health_score ?? 0);
  const risk = health.risk_level || data.risk_level || "UNKNOWN";
  const ecosystems = Object.keys(depsData.ecosystems || {});
  const outdated = Number(depsData.outdated_count ?? data.outdated_count ?? countOutdated(deps));
  const vulnerable = Number(depsData.vulnerable_count ?? data.vulnerable_count ?? alerts.length ?? 0);
  const stats = health.summary_stats || {};
  const breakdown = health.breakdown || {};
  const pinned = stats.pinned_count ?? deps.filter((dep: any) => dep.pinning_type && dep.pinning_type !== "unpinned").length;
  const unpinned = stats.unpinned_count ?? deps.filter((dep: any) => !dep.pinning_type || dep.pinning_type === "unpinned").length;
  const direct = deps.filter((dep: any) => !dep.is_transitive).length;
  const transitive = Math.max(0, deps.length - direct);
  const riskMax = Math.max(1, vulnerable, outdated, direct, transitive);
  const repo = normalizeRepoSlug(data.repo || depsData.repo_info?.full_name || "") || data.repo || "";
  const dependencyTableRows = dependencyRows(deps, alerts);
  const alertRows = dependencyAlertRows(alerts);
  const ecosystemOptions = Array.from(new Set(dependencyTableRows.map((row) => row.ecosystem).filter(Boolean))).sort();
  const filteredRows = dependencyTableRows.filter((row) => {
    const matchesQuery = !query.trim() || row.search.includes(query.trim().toLowerCase());
    const matchesStatus = statusFilter === "all" || row.status === statusFilter;
    const matchesEcosystem = ecosystemFilter === "all" || row.ecosystem === ecosystemFilter;
    const matchesScope = scopeFilter === "all" || row.scope === scopeFilter || row.depth === scopeFilter;
    return matchesQuery && matchesStatus && matchesEcosystem && matchesScope;
  });
  const visibleRows = filteredRows.slice(0, 250);
  const analyzerWarnings = asArray(depsData.errors).length;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-zinc-200 bg-white p-5">
        <SharedSectionHeader
          eyebrow="Dependency score summary"
          title="Supply-chain health"
          description="Package inventory, risk signals, and ecosystem coverage are separated from the architecture map below."
          action={<SharedStatusPill tone={scoreTone(score) as any} label={`${humanize(risk)} ${Math.round(score || 0)}/100`} />}
        />
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <SharedMetricCard label="Dependency score" value={Math.round(score || 0)} hint={humanize(risk)} icon={ShieldCheck} tone={scoreTone(score) as any} />
          <SharedMetricCard label="Packages" value={formatNumber(deps.length || data.total_dependencies)} hint="Detected package rows" icon={Package} tone={deps.length ? "info" : "neutral"} />
          <SharedMetricCard label="Alerts" value={formatNumber(alerts.length || vulnerable)} hint="Dependabot/security alerts" icon={AlertTriangle} tone={alerts.length || vulnerable ? "error" : "success"} />
          <SharedMetricCard label="Outdated" value={formatNumber(outdated)} hint="Version drift" icon={Clock3} tone={outdated ? "warning" : "success"} />
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card>
          <CardHeader>
            <SharedSectionHeader
              eyebrow="Risk"
              title="Dependency risk distribution"
              description="How the package set breaks down by risk and scope."
            />
          </CardHeader>
          <CardContent className="space-y-3">
            <MetricBar label="Vulnerable" value={vulnerable || alerts.length} max={riskMax} tone="error" />
            <MetricBar label="Outdated" value={outdated} max={riskMax} tone="warning" />
            <MetricBar label="Direct" value={direct} max={riskMax} tone="info" />
            <MetricBar label="Transitive" value={transitive} max={riskMax} tone="neutral" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <SharedSectionHeader
              eyebrow="Ecosystems"
              title="Language package systems"
              description="Manifests, lockfiles, and dependency counts grouped by ecosystem."
              action={<Pill themed>{ecosystems.length} ecosystems</Pill>}
            />
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-2">
            {ecosystems.length ? ecosystems.map((name) => (
              <EcosystemCard key={name} name={name} info={depsData.ecosystems[name] || {}} />
            )) : <SharedEmptyState title="No manifests detected" message="The dependency module did not return supported ecosystem manifests." icon={Package} />}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Scoring details</CardTitle>
              <CardDescription>Health score breakdown returned by the dependency module.</CardDescription>
            </div>
            <Pill themed>
              <PillIndicator variant={scoreTone(score)} />
              {humanize(risk)}
            </Pill>
          </div>
        </CardHeader>
        <CardContent>
          <HealthBreakdown breakdown={breakdown} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Security"
            title="Risk and alert table"
            description="Dependabot/security advisories are summarized without exposing complete analyzer internals."
            action={<SharedStatusPill tone={alertRows.length ? "error" : "success"} label={alertRows.length ? `${alertRows.length} alerts` : "No alerts"} />}
          />
        </CardHeader>
        <CardContent>
          <SharedDataTable
            rows={alertRows}
            getRowKey={(row) => row.id}
            columns={[
              { key: "package", header: "Package", render: (row) => <span className="font-mono text-xs font-semibold">{row.pkg}</span> },
              { key: "severity", header: "Severity", render: (row) => <SharedStatusPill tone={severityToTone(row.severity)} label={row.severity.toUpperCase()} /> },
              { key: "ecosystem", header: "Ecosystem", render: (row) => row.ecosystem },
              { key: "range", header: "Affected range", render: (row) => <span className="font-mono text-xs">{row.range}</span> },
              { key: "patched", header: "Patched", render: (row) => <span className="font-mono text-xs">{row.patched}</span> },
              { key: "summary", header: "Summary", render: (row) => <span className="line-clamp-2">{row.summary}</span> },
            ]}
            empty={<SharedEmptyState title="No vulnerability alerts returned" message="The analyzer did not return Dependabot alerts, or this token cannot access them for the repository." icon={Check} />}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Inventory"
            title="Package inventory"
            description="Search and filter the dependency rows returned from manifests and lockfiles."
            action={<Pill themed>{formatNumber(filteredRows.length)} of {formatNumber(dependencyTableRows.length)} rows</Pill>}
          />
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_180px_180px_180px]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-400" />
              <input
                className="h-10 w-full rounded-md border border-zinc-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search packages, versions, files..."
              />
            </label>
            <select className="h-10 rounded-md border border-zinc-300 bg-white px-3 text-sm" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="VULNERABLE">Vulnerable</option>
              <option value="OUTDATED">Outdated</option>
              <option value="UNPINNED">Unpinned</option>
              <option value="PASS">Passing</option>
            </select>
            <select className="h-10 rounded-md border border-zinc-300 bg-white px-3 text-sm" value={ecosystemFilter} onChange={(event) => setEcosystemFilter(event.target.value)}>
              <option value="all">All ecosystems</option>
              {ecosystemOptions.map((ecosystem) => <option key={ecosystem} value={ecosystem}>{ecosystem}</option>)}
            </select>
            <select className="h-10 rounded-md border border-zinc-300 bg-white px-3 text-sm" value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value)}>
              <option value="all">All scopes</option>
              <option value="prod">Production</option>
              <option value="dev">Development</option>
              <option value="direct">Direct</option>
              <option value="transitive">Transitive</option>
            </select>
          </div>

          <SharedDataTable
            rows={visibleRows}
            getRowKey={(row) => row.id}
            columns={[
              { key: "package", header: "Package", render: (row) => <span className="font-mono text-xs font-semibold">{row.name}</span> },
              { key: "version", header: "Version", render: (row) => <span className="font-mono text-xs">{row.version}</span> },
              { key: "ecosystem", header: "Ecosystem", render: (row) => row.ecosystem },
              { key: "source", header: "Source", render: (row) => <span className="font-mono text-xs">{row.source}</span> },
              { key: "scope", header: "Scope", render: (row) => `${row.scope} / ${row.depth}` },
              { key: "pinning", header: "Pinning", render: (row) => row.pinning },
              { key: "latest", header: "Latest", render: (row) => <span className="font-mono text-xs">{row.latest}</span> },
              { key: "status", header: "Status", render: (row) => <SharedStatusPill tone={row.tone} label={row.status} /> },
            ]}
            empty={<SharedEmptyState title="No dependencies match filters" message="Try a broader search, status, ecosystem, or scope filter." icon={Search} />}
          />
          {filteredRows.length > visibleRows.length ? (
            <p className="text-sm text-zinc-500">Showing the first {formatNumber(visibleRows.length)} rows. Narrow the filters to inspect the rest.</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SharedSectionHeader
            eyebrow="Safe diagnostics"
            title="Analyzer diagnostics"
            description="Operational summary only. Detailed analyzer records stay server-side."
            action={<SharedStatusPill tone={analyzerWarnings ? "warning" : "success"} label={analyzerWarnings ? `${analyzerWarnings} warnings` : "No warnings"} />}
          />
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <SummaryRow label="Pinned" value={formatNumber(pinned)} />
          <SummaryRow label="Unpinned" value={formatNumber(unpinned)} />
          <SummaryRow label="Production deps" value={formatNumber(stats.production_deps ?? deps.filter((dep: any) => !dep.is_dev).length)} />
          <SummaryRow label="Dev deps" value={formatNumber(stats.dev_deps ?? deps.filter((dep: any) => dep.is_dev).length)} />
        </CardContent>
      </Card>

      <section className="space-y-3">
        <SharedSectionHeader
          eyebrow="Architecture"
          title="CodeFlow workspace"
          description="Architecture visualization is kept separate from dependency inventory so package triage remains searchable."
        />
        <CodeFlowWorkspace repo={repo} />
      </section>
    </div>
  );
}

function RepoSetupPanel({
  repos,
  auth,
  onRefresh,
  onToast,
}: Readonly<{
  repos: SetupRepository[];
  auth: AuthStatus | null;
  onRefresh: () => Promise<void>;
  onToast: (type: Toast["type"], message: string) => void;
}>) {
  const [repoInput, setRepoInput] = useState("");
  const [busyRepo, setBusyRepo] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [selectedRepoIds, setSelectedRepoIds] = useState<Set<number>>(new Set());

  const selectedCount = selectedRepoIds.size;

  function toggleRepo(repoId: number) {
    setSelectedRepoIds((current) => {
      const next = new Set(current);
      if (next.has(repoId)) next.delete(repoId);
      else next.add(repoId);
      return next;
    });
  }

  function toggleAllRepos(checked: boolean) {
    setSelectedRepoIds(checked ? new Set(repos.map((repo) => repo.id)) : new Set());
  }

  async function registerRepo(event: FormEvent) {
    event.preventDefault();
    const repo = normalizeRepoSlug(repoInput);
    if (!repo) {
      onToast("warning", "Enter a valid owner/repo repository.");
      return;
    }
    setRegistering(true);
    try {
      await apiPost<SetupRepository>("/api/setup/repositories/register", { repo });
      setRepoInput("");
      onToast("success", `${repo} registered.`);
      await onRefresh();
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "Repository registration failed.");
    } finally {
      setRegistering(false);
    }
  }

  async function syncRepos() {
    setSyncing(true);
    try {
      const result = await apiPost<SyncInstallResult>("/api/setup/sync-installed-repositories", { auto_provision: false });
      onToast("success", buildSyncMessage(result));
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, "Repository sync failed. Please retry after a few seconds."));
    } finally {
      setSyncing(false);
    }
  }

  async function provision(repo: SetupRepository) {
    setBusyRepo(repo.id);
    try {
      const result = await apiPost<any>(`/api/setup/repositories/${repo.id}/provision`, {});
      const status = result.status === "pending_pull_request" ? "Setup pull request created." : "Provisioning complete.";
      onToast("success", status);
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, "Provisioning failed. Please retry or verify GitHub App permissions."));
    } finally {
      setBusyRepo(null);
    }
  }

  async function repoAction(repo: SetupRepository, action: "ignore" | "restore" | "deprovision") {
    const labels = { ignore: "ignored", restore: "restored", deprovision: "deprovisioned" };
    if (action === "deprovision") {
      const confirmed = window.confirm(
        `Remove Arya setup from ${repo.full_name}?\n\nThis removes workflow/secrets/ruleset where GitHub permits it. Pipeline history is preserved.`
      );
      if (!confirmed) return;
    }

    setBusyRepo(repo.id);
    try {
      const result = await apiPost<any>(`/api/setup/repositories/${repo.id}/${action}`, {});
      const prUrl = result?.repo?.cleanup_pr_url || result?.result?.workflow_removal?.pull_request_url;
      if (action === "deprovision" && prUrl) {
        onToast("warning", `Cleanup PR created for ${repo.full_name}. Merge it to remove the workflow.`);
      } else {
        onToast("success", `${repo.full_name} ${labels[action]}.`);
      }
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, `${humanize(action)} failed. Please retry.`));
    } finally {
      setBusyRepo(null);
    }
  }

  async function bulkAction(action: "configure" | "ignore" | "deprovision") {
    if (!selectedCount) {
      onToast("warning", "Select at least one repository first.");
      return;
    }
    if (action === "deprovision") {
      const confirmed = window.confirm(
        `Remove Arya setup from ${selectedCount} selected repo${selectedCount === 1 ? "" : "s"}? Pipeline history will be preserved.`
      );
      if (!confirmed) return;
    }

    setSyncing(true);
    try {
      const endpoint = action === "configure" ? "bulk-configure" : action === "ignore" ? "bulk-ignore" : "bulk-deprovision";
      await apiPost(`/api/setup/repositories/${endpoint}`, { repo_ids: [...selectedRepoIds] });
      onToast("success", `${humanize(action)} completed for ${selectedCount} repo${selectedCount === 1 ? "" : "s"}.`);
      setSelectedRepoIds(new Set());
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, `${humanize(action)} failed. Please retry.`));
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <CardDescription className="font-semibold uppercase tracking-wide text-blue-600">
                Repository onboarding
              </CardDescription>
              <CardTitle className="mt-2 text-xl">Configure enforcement for monitored repos</CardTitle>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
                Install the GitHub App, select repositories in GitHub, sync them here, then provision workflow,
                repository secrets, and branch protection through the existing backend.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {auth?.github_app_install_url ? (
                <AnimatedActionButton href={auth.github_app_install_url} target="_blank" rel="noreferrer">
                  <Github className="mr-2 size-4" />
                  Install GitHub App
                </AnimatedActionButton>
              ) : (
                <AnimatedActionButton disabled>Install GitHub App</AnimatedActionButton>
              )}
              <Button variant="outline" onClick={syncRepos} disabled={syncing}>
                {syncing ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCcw className="mr-2 size-4" />}
                Sync Installed Repos
              </Button>
              <Button variant="outline" onClick={() => void onRefresh()}>
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      <form onSubmit={registerRepo} className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 md:flex-row">
        <input
          className="repo-input min-w-0 flex-1"
          placeholder="owner/repo"
          value={repoInput}
          onChange={(event) => setRepoInput(event.target.value)}
        />
        <Button type="submit" variant="outline" disabled={registering}>
          {registering ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
          Register Repo
        </Button>
      </form>

      <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 md:flex-row md:items-center md:justify-between">
        <div className="text-sm text-zinc-600">
          {selectedCount ? `${selectedCount} selected` : "Select repositories to configure, ignore, or undo setup."}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => void bulkAction("configure")} disabled={!selectedCount || syncing}>
            Configure selected
          </Button>
          <Button variant="outline" size="sm" onClick={() => void bulkAction("ignore")} disabled={!selectedCount || syncing}>
            Ignore selected
          </Button>
          <Button variant="outline" size="sm" onClick={() => void bulkAction("deprovision")} disabled={!selectedCount || syncing}>
            Undo setup
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full min-w-[1220px] text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-600">
              <tr>
                <th className="px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label="Select all repositories"
                    checked={repos.length > 0 && selectedRepoIds.size === repos.length}
                    onChange={(event) => toggleAllRepos(event.currentTarget.checked)}
                  />
                </th>
                <th className="px-4 py-3">Repository</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">API Key</th>
                <th className="px-4 py-3">Workflow</th>
                <th className="px-4 py-3">Secrets</th>
                <th className="px-4 py-3">Ruleset</th>
                <th className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {repos.length ? repos.map((repo) => (
                <tr key={repo.id} className="border-b border-zinc-100 align-top">
                  <td className="px-4 py-4">
                    <input
                      type="checkbox"
                      aria-label={`Select ${repo.full_name}`}
                      checked={selectedRepoIds.has(repo.id)}
                      onChange={() => toggleRepo(repo.id)}
                    />
                  </td>
                  <td className="px-4 py-4 font-mono font-semibold">
                    {repo.full_name}
                    {repo.cleanup_pr_url ? (
                      <a className="mt-2 block text-xs font-sans text-blue-600 hover:underline" href={repo.cleanup_pr_url} target="_blank" rel="noreferrer">Cleanup PR #{repo.cleanup_pr_number}</a>
                    ) : null}
                    {repo.setup_pr_url ? (
                      <a className="mt-2 block text-xs font-sans text-blue-600 hover:underline" href={repo.setup_pr_url} target="_blank" rel="noreferrer">Setup PR #{repo.setup_pr_number}</a>
                    ) : null}
                  </td>
                  <td className="px-4 py-4">
                    <Pill themed>
                      <PillIndicator variant={statusTone(repo.setup_status)} />
                      {humanize(repo.setup_status)}
                    </Pill>
                    {repo.last_setup_error ? <p className="mt-2 max-w-xs text-xs text-red-700">{repo.last_setup_error}</p> : null}
                  </td>
                  <td className="px-4 py-4"><Pill themed>{repo.api_key_prefix || "pending"}</Pill></td>
                  <td className="px-4 py-4"><Pill themed><PillIndicator variant={repo.workflow_installed_at ? "success" : "warning"} />{repo.workflow_installed_at ? formatDate(repo.workflow_installed_at) : "Pending"}</Pill></td>
                  <td className="px-4 py-4"><Pill themed><PillIndicator variant={repo.secrets_configured_at ? "success" : "warning"} />{repo.secrets_configured_at ? formatDate(repo.secrets_configured_at) : "Pending"}</Pill></td>
                  <td className="px-4 py-4"><Pill themed><PillIndicator variant={repo.ruleset_configured_at ? "success" : "warning"} />{repo.ruleset_configured_at ? formatDate(repo.ruleset_configured_at) : "Pending"}</Pill></td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => void provision(repo)} disabled={busyRepo === repo.id || repo.setup_status === "ignored" || repo.setup_status === "deprovisioned"}>
                        {busyRepo === repo.id ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Play className="mr-2 size-4" />}
                        Configure
                      </Button>
                      {repo.setup_status === "ignored" || repo.setup_status === "deprovisioned" ? (
                        <Button size="sm" variant="outline" onClick={() => void repoAction(repo, "restore")} disabled={busyRepo === repo.id}>
                          Restore
                        </Button>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => void repoAction(repo, "ignore")} disabled={busyRepo === repo.id}>
                          Ignore
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => void repoAction(repo, "deprovision")} disabled={busyRepo === repo.id}>
                        <Trash2 className="mr-2 size-4" />
                        Undo
                      </Button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">No monitored repositories yet. Install the GitHub App and sync selected repos.</td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function HistoryPanel({
  history,
  onOpen,
  onDelete,
  onClear,
}: Readonly<{
  history: AnalysisHistoryItem[];
  onOpen: (item: AnalysisHistoryItem) => void;
  onDelete: (id: number) => Promise<void>;
  onClear: () => Promise<void>;
}>) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Analysis history</CardTitle>
            <CardDescription>Tenant-scoped database history from AnalysisHistory.</CardDescription>
          </div>
          <Button variant="outline" onClick={() => void onClear()} disabled={!history.length}>
            <Trash2 className="mr-2 size-4" />
            Clear history
          </Button>
        </div>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full min-w-[1100px] text-left text-sm">
          <thead className="border-y border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-600">
            <tr>
              <th className="px-4 py-3">Repository</th>
              <th className="px-4 py-3">Analyzed</th>
              <th className="px-4 py-3">Language</th>
              <th className="px-4 py-3">Health</th>
              <th className="px-4 py-3">CI/CD</th>
              <th className="px-4 py-3">Deps</th>
              <th className="px-4 py-3">Exports</th>
              <th className="px-4 py-3">Action</th>
            </tr>
          </thead>
          <tbody>
            {history.length ? history.map((item) => (
              <tr key={item.id} className="border-b border-zinc-100 hover:bg-zinc-50">
                <td className="px-4 py-3 font-mono font-semibold">{item.repo}</td>
                <td className="whitespace-nowrap px-4 py-3">{formatDate(item.analyzed_at)}</td>
                <td className="px-4 py-3">{item.language || "Unknown"}</td>
                <td className="px-4 py-3"><Pill themed><PillIndicator variant={scoreTone(item.health_score)} />{item.health_score ?? "N/A"}</Pill></td>
                <td className="px-4 py-3">{(item.cicd_platforms || []).join(", ") || "None"}</td>
                <td className="px-4 py-3">{formatNumber(item.total_dependencies)} total, {formatNumber(item.vulnerable_count)} vulnerable</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <a className="text-blue-600 hover:underline" href={`/api/history/${item.id}/export?format=json`}><Download className="inline size-3.5" /> JSON</a>
                    <a className="text-blue-600 hover:underline" href={`/api/history/${item.id}/export?format=markdown`}><Download className="inline size-3.5" /> MD</a>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => onOpen(item)}>Open</Button>
                    <Button size="sm" variant="ghost" onClick={() => void onDelete(item.id)}>Delete</Button>
                  </div>
                </td>
              </tr>
            )) : (
              <tr><td colSpan={8} className="px-4 py-8 text-center text-zinc-600">No history yet.</td></tr>
            )}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function ToastStack({ toasts, onDismiss }: Readonly<{ toasts: Toast[]; onDismiss: (id: number) => void }>) {
  return (
    <div className="fixed bottom-5 right-5 z-50 flex w-[min(420px,calc(100vw-32px))] flex-col gap-2">
      {toasts.map((toast) => (
        <div key={toast.id} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-lg">
          <div className="flex items-start gap-3">
            <PillIndicator variant={toast.type === "success" ? "success" : toast.type === "error" ? "error" : toast.type === "warning" ? "warning" : "info"} />
            <p className="min-w-0 flex-1 text-sm text-zinc-800">{toast.message}</p>
            <button className="text-zinc-500 hover:text-zinc-900" onClick={() => onDismiss(toast.id)}>x</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function LandingPage({
  auth,
  onOpenDashboard,
  toasts,
  onDismissToast,
}: Readonly<{
  auth: AuthStatus | null;
  onOpenDashboard: () => void;
  toasts: Toast[];
  onDismissToast: (id: number) => void;
}>) {
  const signedIn = Boolean(auth?.authenticated);
  const loginConfigured = auth?.github_login_configured !== false;

  const PLATFORM_STATS = [
    { value: "9", label: "CI/CD Platforms" },
    { value: "7", label: "Language Ecosystems" },
    { value: "16", label: "Security Rules" },
    { value: "5", label: "Analysis Modules" },
  ];

  const FEATURES = [
    {
      tag: "Module 01",
      title: "Repository Metadata",
      description: "Extract repository facts, stars, forks, language distribution, topics, full commit history timeline, top contributors with contribution counts, and complete file tree structure.",
      capabilities: ["Commit timeline", "Contributor ranking", "File tree", "README rendering"],
    },
    {
      tag: "Module 02",
      title: "CI/CD Pipeline Analysis",
      description: "Detect and analyze pipelines across GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, Travis CI, Drone CI, Bitbucket Pipelines, and TeamCity.",
      capabilities: ["Platform detection", "Job structure parsing", "Security grading A–F", "Complexity scoring"],
    },
    {
      tag: "Module 03",
      title: "Dependency Health",
      description: "Detect ecosystems across Python, Node.js, Java, Go, Rust, Ruby, and PHP. Parse manifests and lockfiles with health scoring from 0 to 100.",
      capabilities: ["7 ecosystem parsers", "Dependabot alerts", "Version drift", "Risk scoring"],
    },
    {
      tag: "Module 04",
      title: "Autonomous Quality Gates",
      description: "Run secret detection, linting, SAST, dependency audits, code quality checks, file scanning, and type checking automatically via GitHub Actions.",
      capabilities: ["Gitleaks + Semgrep", "Pre-commit hooks", "Quality verdicts", "Report ingestion"],
    },
    {
      tag: "Module 05",
      title: "DevSecOps Pipeline",
      description: "End-to-end autonomous pipeline from quality gate to compiler check to AI remediation. GitHub Actions enforces, branch protection controls merge eligibility.",
      capabilities: ["GitHub App automation", "Branch protection", "Secret redaction", "Stage tracking"],
    },
    {
      tag: "Module 06",
      title: "Multi-Tenant Dashboard",
      description: "Tenant-scoped workspaces with GitHub OAuth, SSE live progress streaming, tabbed interface, analysis history, and batch repository analysis.",
      capabilities: ["Tenant isolation", "SSE streaming", "Batch analysis", "History & export"],
    },
  ];

  const PIPELINE_STEPS = [
    { step: "01", title: "Install App", description: "Client installs GitHub App and selects repos" },
    { step: "02", title: "Sync Repos", description: "Backend records installation and syncs repositories" },
    { step: "03", title: "Add Workflow", description: "Backend provisions workflow YAML and secrets" },
    { step: "04", title: "Set Rulesets", description: "Branch protection and required status checks configured" },
    { step: "05", title: "Push / PR", description: "Developer pushes code or opens pull request" },
    { step: "06", title: "Quality Gate", description: "Code-Quality scanner runs via GitHub Actions" },
    { step: "07", title: "Report", description: "Results sent to dashboard, merge blocked or allowed" },
  ];

  const SECURITY_ITEMS = [
    { title: "Repo-scoped API keys", description: "Dashboard API keys stored as GitHub Secrets per repository" },
    { title: "Secret redaction", description: "Raw secret values replaced with [REDACTED] before storage, UI, or AI" },
    { title: "Tenant-scoped history", description: "Pipeline runs and analysis results isolated per tenant workspace" },
    { title: "Required status checks", description: "GitHub Actions workflow must pass before merge into protected branches" },
    { title: "Webhook verification", description: "X-Hub-Signature-256 validated against WEBHOOK_SECRET for all payloads" },
    { title: "Payload guardrails", description: "Rate limiting, size limits, repo allowlisting, and duplicate handling" },
  ];

  const TECH_STACK = [
    { layer: "Backend", tech: "Python 3.11+, FastAPI, Uvicorn" },
    { layer: "Database", tech: "SQLite via SQLAlchemy ORM + Alembic" },
    { layer: "Frontend", tech: "React, TypeScript, Vite, Tailwind CSS" },
    { layer: "API", tech: "GitHub REST API v3, Server-Sent Events" },
    { layer: "Scanner", tech: "Gitleaks, Semgrep, Bandit, Ruff, pip-audit" },
    { layer: "Orchestration", tech: "GitHub Actions + Branch Protection" },
  ];

  return (
    <div className="min-h-screen bg-white text-zinc-950">
      {/* ─── Navbar ─────────────────────────────────────────────── */}
      {/* ─── Navbar ─────────────────────────────────────────────── */}
      <GlassFilter />
      <header className="sticky top-4 z-50 mx-auto max-w-6xl px-4 sm:px-6 mb-8 mt-4">
        <GlassEffect className="rounded-2xl px-6 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-zinc-900 text-sm font-bold text-white shadow-inner">RI</div>
              <div className="leading-tight">
                <div className="text-sm font-bold tracking-tight">Repo Intelligence</div>
                <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-600">Arya Technologies</div>
              </div>
            </div>

            <nav className="hidden items-center gap-8 text-sm font-semibold text-zinc-700 md:flex">
              <a href="#features" className="transition-all duration-300 hover:text-zinc-950 hover:scale-105">Features</a>
              <a href="#workflow" className="transition-all duration-300 hover:text-zinc-950 hover:scale-105">How It Works</a>
              <a href="#architecture" className="transition-all duration-300 hover:text-zinc-950 hover:scale-105">Architecture</a>
              <a href="#security" className="transition-all duration-300 hover:text-zinc-950 hover:scale-105">Security</a>
            </nav>

            <div className="flex items-center gap-3">
              {signedIn ? (
                <AnimatedActionButton onClick={onOpenDashboard}>Open Dashboard</AnimatedActionButton>
              ) : loginConfigured ? (
                <AnimatedActionButton href={authLoginHref()}>
                  <Github className="mr-2 size-4" />
                  Sign in with GitHub
                </AnimatedActionButton>
              ) : (
                <AnimatedActionButton disabled>OAuth not configured</AnimatedActionButton>
              )}
            </div>
          </div>
        </GlassEffect>
      </header>

      <main>
        {/* ─── Hero ──────────────────────────────────────────────── */}
        <section className="pb-20 pt-10 lg:pt-16">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
            {/* Left — copy */}
            <div className="animate-fade-in-up">
              <p className="text-sm font-semibold uppercase tracking-widest text-blue-600">
                Repository quality platform
              </p>
              <h1 className="mt-5 text-4xl font-semibold leading-tight tracking-tight text-zinc-950 lg:text-5xl">
                GitHub enforcement, intelligence, and reporting in one place.
              </h1>
              <p className="mt-6 text-lg leading-relaxed text-zinc-500 pr-4">
                A unified command center for repository metadata, CI/CD analysis, dependency health, autonomous quality gates, and DevSecOps pipeline enforcement.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-4">
                {signedIn ? (
                  <Button size="lg" onClick={onOpenDashboard}>
                    Open Dashboard
                  </Button>
                ) : (
                  <Button asChild size="lg" disabled={!loginConfigured}>
                    <a href={loginConfigured ? authLoginHref() : "#"}>
                      <Github className="mr-2 size-5" />
                      Sign in with GitHub
                    </a>
                  </Button>
                )}
                <Button variant="outline" size="lg" onClick={() => document.getElementById("features")?.scrollIntoView({ behavior: "smooth" })}>
                  Explore features
                </Button>
              </div>

              {signedIn ? (
                <div className="mt-6 flex flex-wrap gap-2">
                  <Pill themed>
                    <PillIndicator variant="success" />
                    Signed in as {auth?.user?.github_login || "GitHub user"}
                  </Pill>
                  <Pill themed>{auth?.tenants?.length || 0} workspace(s)</Pill>
                </div>
              ) : null}
            </div>

            {/* Right — feature bullets */}
            <div className="relative flex flex-col justify-center space-y-6 lg:pl-8 -translate-y-4 lg:-translate-y-12">
              {/* Dashed vertical separator */}
              <div className="dashed-line-v absolute left-0 top-0 text-zinc-200 max-lg:hidden" />
              {/* Dashed horizontal separator for mobile */}
              <div className="dashed-line-h text-zinc-200 lg:hidden" />

              <div className="animate-fade-in-up-delay-1 space-y-6 py-4 flex justify-center lg:justify-start lg:pl-10">
                <DisplayCards
                  cards={[
                    {
                      icon: <BarChart3 className="size-4 text-blue-300" />,
                      title: "Repo Intelligence",
                      description: "Metadata & CI/CD Analytics",
                      date: "9 pipeline platforms",
                      iconClassName: "text-blue-500",
                      titleClassName: "text-blue-500",
                      className: "[grid-area:stack] hover:-translate-y-10 before:absolute before:w-[100%] before:outline-1 before:rounded-xl before:outline-border before:h-[100%] before:content-[''] before:bg-blend-overlay before:bg-background/50 grayscale-[100%] hover:before:opacity-0 before:transition-opacity before:duration:700 hover:grayscale-0 before:left-0 before:top-0",
                    },
                    {
                      icon: <Package className="size-4 text-purple-300" />,
                      title: "Dependency Security",
                      description: "SBOM & Vulnerability Alerts",
                      date: "7 ecosystems supported",
                      iconClassName: "text-purple-500",
                      titleClassName: "text-purple-500",
                      className: "[grid-area:stack] translate-x-12 translate-y-10 hover:-translate-y-1 before:absolute before:w-[100%] before:outline-1 before:rounded-xl before:outline-border before:h-[100%] before:content-[''] before:bg-blend-overlay before:bg-background/50 grayscale-[100%] hover:before:opacity-0 before:transition-opacity before:duration:700 hover:grayscale-0 before:left-0 before:top-0",
                    },
                    {
                      icon: <ShieldCheck className="size-4 text-emerald-300" />,
                      title: "Quality Gates",
                      description: "Pre-commit & GitHub Actions",
                      date: "Gitleaks, Semgrep, AST",
                      iconClassName: "text-emerald-500",
                      titleClassName: "text-emerald-500",
                      className: "[grid-area:stack] translate-x-24 translate-y-20 hover:translate-y-10",
                    },
                  ]}
                />
              </div>
            </div>
          </div>
          {/* Hero Dashboard Mockup */}
          <div className="mx-auto mt-16 max-w-7xl px-6 lg:mt-20 translate-x-2">
            <HeroDashboardMockup />
          </div>
        </section>

        {/* ─── Stats ribbon ──────────────────────────────────────── */}
        <section className="border-y border-zinc-200 bg-zinc-50">
          <div className="mx-auto grid max-w-7xl grid-cols-2 md:grid-cols-4">
            {PLATFORM_STATS.map((stat, i) => (
              <div key={stat.label} className={`px-6 py-8 text-center ${i < PLATFORM_STATS.length - 1 ? "border-r border-zinc-200 max-md:[&:nth-child(2)]:border-r-0" : ""} ${i < 2 ? "max-md:border-b max-md:border-zinc-200" : ""}`}>
                <div className="text-3xl font-semibold tracking-tight text-zinc-950">{stat.value}</div>
                <div className="mt-1 text-sm text-zinc-500">{stat.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Features ──────────────────────────────────────────── */}
        <section id="features" className="py-20 lg:py-28">
          <div className="mx-auto max-w-7xl px-6">
            {/* Section header */}
            <div className="relative flex items-center justify-center">
              <div className="dashed-line-h text-zinc-300" />
              <span className="absolute bg-white px-4 font-mono text-xs font-medium uppercase tracking-widest text-zinc-400">
                Platform Modules
              </span>
            </div>

            <div className="mx-auto mt-10 grid max-w-4xl items-center gap-3 md:gap-0 lg:mt-16 lg:grid-cols-2">
              <h2 className="text-2xl font-semibold tracking-tight md:text-3xl lg:text-4xl">
                Six analysis modules, one unified platform.
              </h2>
              <p className="text-zinc-500 leading-relaxed">
                Each module runs independently or as part of a combined analysis. Enter <span className="font-mono text-zinc-700">owner/repo</span> and get metadata, CI/CD, dependency health, quality gate results, and pipeline state streamed via SSE.
              </p>
            </div>

            {/* Feature grid */}
            <div className="mt-12 lg:mt-16">
              <div className="dashed-line-h text-zinc-200" />

              <div className="grid md:grid-cols-2 lg:grid-cols-3">
                {FEATURES.map((feature, i) => (
                  <div key={feature.tag} className={`relative flex flex-col justify-between p-6 md:p-8 ${(i + 1) % 3 !== 0 ? "lg:border-r lg:border-zinc-200" : ""} ${(i + 1) % 2 !== 0 ? "max-lg:border-r max-lg:border-zinc-200 max-md:border-r-0" : ""} ${i < FEATURES.length - 3 ? "lg:border-b lg:border-zinc-200" : ""} ${i < FEATURES.length - 2 ? "max-lg:border-b max-lg:border-zinc-200 max-md:border-b" : ""}`}>
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-widest text-blue-600">{feature.tag}</div>
                      <h3 className="mt-3 text-lg font-semibold tracking-tight">{feature.title}</h3>
                      <p className="mt-2 text-sm leading-relaxed text-zinc-500">{feature.description}</p>
                    </div>
                    <div className="mt-5 flex flex-wrap gap-1.5">
                      {feature.capabilities.map((cap) => (
                        <span key={cap} className="rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-600">{cap}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div className="dashed-line-h text-zinc-200" />
            </div>
          </div>
        </section>

        {/* ─── How It Works / Pipeline flow ───────────────────────── */}
        <section id="workflow" className="border-t border-zinc-200 bg-zinc-50 py-20 lg:py-28">
          <div className="mx-auto max-w-7xl px-6">
            <div className="mx-auto max-w-3xl text-center">
              <p className="text-sm font-semibold uppercase tracking-widest text-blue-600">Autonomous onboarding</p>
              <h2 className="mt-4 text-2xl font-semibold tracking-tight md:text-3xl lg:text-4xl">
                From GitHub App install to enforced repository protection.
              </h2>
              <p className="mx-auto mt-4 max-w-2xl text-zinc-500 leading-relaxed">
                Clients sign in with GitHub and select repositories. The backend automatically provisions workflow files, secrets, and branch rulesets — zero manual configuration.
              </p>
            </div>

            <div className="mt-12 lg:mt-16">
              <div className="dashed-line-h text-zinc-300" />
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7">
                {PIPELINE_STEPS.map((item, i) => (
                  <div key={item.step} className={`relative p-5 md:p-6 ${i < PIPELINE_STEPS.length - 1 ? "border-r border-zinc-200 max-lg:[&:nth-child(4)]:border-r-0 max-md:[&:nth-child(2)]:border-r-0 max-md:[&:nth-child(4)]:border-r-0 max-md:[&:nth-child(6)]:border-r-0" : ""} ${i >= 4 ? "lg:border-t-0" : ""} max-lg:border-b max-lg:border-zinc-200 lg:border-b-0`}>
                    <div className="text-xs font-semibold text-blue-600">{item.step}</div>
                    <div className="mt-2 font-semibold text-sm text-zinc-950">{item.title}</div>
                    <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">{item.description}</p>
                  </div>
                ))}
              </div>
              <div className="dashed-line-h text-zinc-300" />
            </div>

            {/* Enforcement callout */}
            <div className="mx-auto mt-10 max-w-3xl rounded-xl border border-zinc-200 bg-white p-6">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 size-5 shrink-0 text-blue-600" />
                <div>
                  <div className="text-sm font-semibold text-zinc-950">Enforcement model</div>
                  <p className="mt-1 text-sm leading-relaxed text-zinc-500">
                    Local pre-commit hooks provide developer convenience. GitHub Actions with branch protection provides mandatory company-level enforcement. The dashboard receives reports — it does not replace the CI runner.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Business Value / ROI ──────────────────────────── */}
        <section id="benefits" className="py-20 lg:py-28">
          <div className="mx-auto max-w-7xl px-6">
            <div className="relative flex items-center justify-center">
              <div className="dashed-line-h text-zinc-300" />
              <span className="absolute bg-white px-4 font-mono text-xs font-medium uppercase tracking-widest text-zinc-400">
                Business Value
              </span>
            </div>

            <div className="mx-auto mt-10 grid max-w-5xl gap-8 lg:mt-16 lg:grid-cols-[1.2fr_1fr] lg:gap-16">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
                  Protect your main branch. Empower your engineering teams.
                </h2>
                <p className="mt-4 text-zinc-500 leading-relaxed">
                  Repo Intelligence is built for engineering leaders who need absolute certainty that every pull request meets security, quality, and architectural standards before it merges.
                </p>

                <div className="mt-8 space-y-6">
                  <div className="flex gap-4">
                    <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
                      <ShieldCheck className="size-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-950">Zero-Trust Quality Gates</h4>
                      <p className="mt-1 text-sm text-zinc-500">Autonomous pipelines run security and linting checks on every push, directly blocking non-compliant code from merging.</p>
                    </div>
                  </div>

                  <div className="flex gap-4">
                    <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-100">
                      <BarChart3 className="size-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-950">Unified Executive Reporting</h4>
                      <p className="mt-1 text-sm text-zinc-500">View dependency health, CI/CD pipeline stats, and security vulnerabilities across your entire organization in one centralized dashboard.</p>
                    </div>
                  </div>

                  <div className="flex gap-4">
                    <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-600 border border-indigo-100">
                      <Package className="size-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-zinc-950">Seamless GitHub Integration</h4>
                      <p className="mt-1 text-sm text-zinc-500">Installs in seconds. No complex local setups required for your developers—it just works in the background via GitHub Actions.</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Client ROI Card */}
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-1.5 h-fit mt-8 lg:mt-0">
                <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-6">Why Clients Choose Us</div>

                  <div className="space-y-5">
                    <div>
                      <div className="text-2xl font-bold text-zinc-950">99.9%</div>
                      <div className="text-sm text-zinc-500">Reduction in merged vulnerabilities</div>
                    </div>
                    <div className="dashed-line-h text-zinc-100" />
                    <div>
                      <div className="text-2xl font-bold text-zinc-950">&lt; 3 mins</div>
                      <div className="text-sm text-zinc-500">Average time to detect and block bad code</div>
                    </div>
                    <div className="dashed-line-h text-zinc-100" />
                    <div>
                      <div className="text-2xl font-bold text-zinc-950">Day One</div>
                      <div className="text-sm text-zinc-500">Immediate ROI with zero developer onboarding</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── Security ──────────────────────────────────────────── */}
        <section id="security" className="border-t border-zinc-200 bg-zinc-950 text-white">
          <div className="mx-auto max-w-7xl px-6 py-20 lg:py-28">
            <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
              <div>
                <p className="text-sm font-semibold uppercase tracking-widest text-blue-400">Security model</p>
                <h2 className="mt-4 text-2xl font-semibold tracking-tight md:text-3xl">
                  Company-level enforcement belongs in GitHub Actions and branch protection.
                </h2>
                <p className="mt-4 text-sm leading-relaxed text-zinc-400">
                  Local hooks provide early feedback but can be bypassed. Production enforcement uses GitHub Actions as the mandatory trigger with Required Status Checks controlling merge eligibility. The dashboard stores and displays — it does not replace the runner.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {SECURITY_ITEMS.map((item) => (
                  <div key={item.title} className="rounded-lg border border-white/10 bg-white/5 p-4">
                    <div className="text-sm font-semibold">{item.title}</div>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-400">{item.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ─── CTA ───────────────────────────────────────────────── */}
        <section className="border-b border-zinc-200">
          <div className="mx-auto max-w-7xl px-6 py-20 text-center lg:py-28">
            <h2 className="text-2xl font-semibold tracking-tight md:text-3xl lg:text-4xl">
              Start analyzing repositories today.
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-zinc-500 leading-relaxed">
              Sign in with GitHub, select your repositories, and get metadata, CI/CD, dependency health, and quality pipeline results in one dashboard.
            </p>
          </div>
        </section>
      </main>

      {/* ─── Footer ──────────────────────────────────────────────── */}
      <footer className="border-t border-zinc-200 bg-white">
        <div className="mx-auto max-w-7xl px-6 py-10">
          <div className="flex flex-col items-center gap-6 md:flex-row md:justify-between">
            <div className="flex items-center gap-3">
              <div className="grid size-8 place-items-center rounded-md bg-zinc-900 text-xs font-bold text-white">RI</div>
              <div className="leading-tight">
                <div className="text-sm font-semibold">Repo Intelligence</div>
                <div className="text-xs text-zinc-500">Arya Technologies</div>
              </div>
            </div>
            <nav className="flex flex-wrap items-center justify-center gap-6 text-sm font-medium text-zinc-600">
              <a href="#features" className="transition-opacity hover:opacity-75">Features</a>
              <a href="#workflow" className="transition-opacity hover:opacity-75">How It Works</a>
              <a href="#architecture" className="transition-opacity hover:opacity-75">Architecture</a>
              <a href="#security" className="transition-opacity hover:opacity-75">Security</a>
            </nav>
          </div>
          <div className="dashed-line-h mt-8 text-zinc-200" />
          <div className="mt-6 flex flex-col items-center gap-2 text-xs text-zinc-400 md:flex-row md:justify-between">
            <span>GitHub-native quality, intelligence, and reporting platform.</span>
            <span>Internal project — Arya Technologies</span>
          </div>
        </div>
      </footer>

      <ToastStack toasts={toasts} onDismiss={onDismissToast} />
    </div>
  );
}

export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(false);
  const [view, setView] = useState<ViewKey>(() => routeFromLocation());
  const [activeTab, setActiveTab] = useState<TabKey>(() => moduleFromLocation());
  const [repoInput, setRepoInput] = useState("");
  const [batchInput, setBatchInput] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [historyItems, setHistoryItems] = useState<AnalysisHistoryItem[]>([]);
  const [setupRepos, setSetupRepos] = useState<SetupRepository[]>([]);
  const [rateLimit, setRateLimit] = useState<Record<string, any> | null>(null);
  const [progress, setProgress] = useState<ProgressLine[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeButtonStatus, setAnalyzeButtonStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [batchRunning, setBatchRunning] = useState(false);
  const [mode, setMode] = useState<"single" | "batch">("single");
  const [toasts, setToasts] = useState<Toast[]>([]);

  const authenticated = auth ? Boolean(auth.authenticated || !auth.require_login) : false;

  function showToast(type: Toast["type"], message: string) {
    const id = Date.now() + Math.random();
    setToasts((items) => [...items, { id, type, message }].slice(-4));
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 5200);
  }

  async function loadAuth() {
    try {
      setAuth(await apiGet<AuthStatus>("/api/auth/status"));
    } catch {
      setAuth(null);
    } finally {
      setAuthLoading(false);
    }
  }

  async function loadRateLimit() {
    try {
      setRateLimit(await apiGet<Record<string, any>>("/api/rate-limit"));
    } catch {
      setRateLimit(null);
    }
  }

  async function loadHistory() {
    try {
      setHistoryItems(await apiGet<AnalysisHistoryItem[]>("/api/history"));
    } catch (error) {
      if (auth?.authenticated) showToast("error", error instanceof Error ? error.message : "Could not load history.");
    }
  }

  async function loadSetupRepos() {
    try {
      setSetupRepos(await apiGet<SetupRepository[]>("/api/setup/repositories"));
    } catch (error) {
      if (auth?.authenticated) showToast("error", error instanceof Error ? error.message : "Could not load setup repositories.");
    }
  }

  useEffect(() => {
    void loadAuth();
    void loadRateLimit();
  }, []);

  useEffect(() => {
    if (authenticated) {
      void loadHistory();
      void loadSetupRepos();
    }
  }, [authenticated, auth?.selected_tenant_id]);

  async function logout() {
    await apiPost("/api/auth/logout", {});
    setAuth(null);
    setAnalysis(null);
    showToast("success", "Logged out.");
    await loadAuth();
  }

  async function selectTenant(tenantId: string) {
    try {
      await apiPost("/api/auth/select-tenant", { tenant_id: Number(tenantId) });
      showToast("success", "Tenant selected.");
      await loadAuth();
      await loadHistory();
      await loadSetupRepos();
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "Tenant selection failed.");
    }
  }

  async function enrichMetadataDetails(nextAnalysis: AnalysisPayload) {
    const repoId = nextAnalysis.metadata?.repo_id;
    if (!repoId) return;
    try {
      const details = await apiGet<Record<string, any>>(`/api/meta/repos/${repoId}/metrics`);
      setAnalysis((current) => current && current.history_id === nextAnalysis.history_id ? { ...current, metadata_details: details } : current);
    } catch {
      // Deep metadata is optional; the core analysis remains valid.
    }
  }

  async function runAnalysis(event?: FormEvent) {
    event?.preventDefault();
    const repo = normalizeRepoSlug(repoInput);
    if (!repo) {
      showToast("warning", "Enter a valid GitHub repository, URL, or .git URL.");
      return;
    }
    setRepoInput(repo);
    setAnalyzing(true);
    setAnalyzeButtonStatus("loading");
    setProgress([]);
    openModule("overview", true);
    let finalData: AnalysisPayload | null = null;
    try {
      await streamPost("/api/analyze/full", { repo }, ({ event: eventName, data }: StreamEvent<any>) => {
        if (eventName === "progress") {
          setProgress((items) => [
            ...items.slice(-80),
            {
              id: Date.now() + Math.random(),
              module: data.module || "system",
              message: data.data || data.error || data.event || "progress",
              level: data.level,
            },
          ]);
        }
        if (eventName === "done") finalData = data;
        if (eventName === "error") throw new Error(data.error || "Analysis failed.");
      });
      const normalized = normalizeAnalysisPayload(finalData);
      setAnalysis(normalized);
      showToast("success", normalized?.cache_hit ? "Loaded cached analysis." : "Repository analysis complete.");
      setAnalyzeButtonStatus("success");
      if (normalized) void enrichMetadataDetails(normalized);
      await loadHistory();
    } catch (error) {
      setAnalyzeButtonStatus("error");
      showToast("error", error instanceof Error ? error.message : "Analysis failed.");
    } finally {
      setAnalyzing(false);
      setTimeout(() => setAnalyzeButtonStatus("idle"), 2000);
    }
  }

  async function runBatchAnalysis() {
    const repos = Array.from(
      new Set(batchInput.split(/\r?\n/).map(normalizeRepoSlug).filter(Boolean)),
    );
    if (!repos.length) {
      showToast("warning", "Add at least one valid repository.");
      return;
    }
    setBatchRunning(true);
    setProgress([]);
    const batchId = `batch_${Date.now()}`;
    try {
      await streamPost("/api/batch/analyze", { repos, batch_id: batchId }, ({ event: eventName, data }: StreamEvent<any>) => {
        if (eventName === "batch_progress") {
          setProgress((items) => [...items, { id: Date.now() + Math.random(), module: "batch", message: `Analyzing ${data.repo} (${data.current}/${data.total})` }]);
        }
        if (eventName === "progress") {
          setProgress((items) => [...items.slice(-80), { id: Date.now() + Math.random(), module: data.module || "system", message: data.data || data.event || "progress", level: data.level }]);
        }
        if (eventName === "done") {
          setAnalysis(normalizeAnalysisPayload(data));
        }
      });
      showToast("success", "Batch analysis complete.");
      await loadHistory();
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "Batch analysis failed.");
    } finally {
      setBatchRunning(false);
    }
  }

  async function openHistory(item: AnalysisHistoryItem) {
    try {
      const record = await apiGet<AnalysisHistoryItem>(`/api/history/${item.id}`);
      const normalized = normalizeAnalysisPayload(record as AnalysisPayload);
      setAnalysis(normalized);
      setRepoInput(item.repo);
      openModule("overview", true);
      if (normalized && !normalized.metadata_details) void enrichMetadataDetails(normalized);
      showToast("success", "History record loaded.");
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "Could not open history item.");
    }
  }

  async function deleteHistory(id: number) {
    await apiDelete(`/api/history/${id}`);
    showToast("success", "History item deleted.");
    await loadHistory();
  }

  async function clearHistory() {
    await apiDelete("/api/history");
    showToast("success", "History cleared.");
    await loadHistory();
  }

  const recentHistory = useMemo(() => historyItems.slice(0, 4), [historyItems]);

  useEffect(() => {
    const onPopState = () => {
      setView(routeFromLocation());
      setActiveTab(moduleFromLocation());
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function navigate(nextView: ViewKey, tab: TabKey = "overview") {
    const path = nextView === "dashboard" ? dashboardPath(tab) : "/react/";
    window.history.pushState(null, "", path);
    setView(nextView);
    if (nextView === "dashboard") setActiveTab(tab);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function openModule(tab: TabKey, replace = false) {
    const path = dashboardPath(tab);
    if (window.location.pathname !== path) {
      if (replace) window.history.replaceState(null, "", path);
      else window.history.pushState(null, "", path);
    }
    setView("dashboard");
    setActiveTab(tab);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <Loader2 className="size-6 animate-spin text-zinc-400" />
      </div>
    );
  }

  if (view === "landing" || !authenticated) {
    return (
      <LandingPage
        auth={auth}
        onOpenDashboard={() => navigate("dashboard")}
        toasts={toasts}
        onDismissToast={(id) => setToasts((items) => items.filter((item) => item.id !== id))}
      />
    );
  }

  const activeModule = MODULE_BY_KEY[activeTab];
  const activeRepo =
    normalizeRepoSlug(analysis?.repo || repoInput) ||
    analysis?.repo ||
    repoInput ||
    "";
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950">
      <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/95 backdrop-blur">
        <div className="flex min-h-20 items-center gap-6 px-6">
          <button
            className="flex w-64 shrink-0 items-center gap-3 text-left transition-opacity hover:opacity-80"
            onClick={() => navigate("landing")}
          >
            <div className="grid size-10 place-items-center rounded-md bg-zinc-900 text-sm font-bold text-white">RI</div>
            <div>
              <div className="text-lg font-semibold leading-tight">Repo Intelligence</div>
              <div className="text-sm text-zinc-600">Arya Technologies</div>
            </div>
          </button>

          <form onSubmit={runAnalysis} className="hidden min-w-0 flex-1 items-center md:flex">
            <div className="flex w-full max-w-xl overflow-hidden rounded-lg border border-zinc-300 bg-white shadow-sm">
              <span className="flex items-center border-r border-zinc-200 px-3 text-sm font-semibold text-blue-600">repo</span>
              <input
                className="min-w-0 flex-1 px-3 py-2 font-mono text-sm outline-none"
                placeholder="owner/repo, GitHub URL, or .git URL"
                value={repoInput}
                onChange={(event) => setRepoInput(event.target.value)}
              />
              <AnimatedAnalyzeButton type="submit" status={analyzeButtonStatus} />
            </div>
          </form>

          <div className="ml-auto flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => window.location.reload()} title="Refresh page" className="h-9 px-3 gap-1.5 text-zinc-600 hover:text-zinc-900 bg-white border border-zinc-200 shadow-sm rounded-full">
              <RefreshCcw className="size-4" />
              <span className="font-medium text-sm">Refresh</span>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-full overflow-hidden border border-zinc-200 hover:border-zinc-300 shadow-sm transition-colors cursor-pointer outline-none p-0">
                  {auth?.user?.avatar_url ? (
                    <img src={auth.user.avatar_url} alt="Profile" className="size-full object-cover" />
                  ) : (
                    <User className="size-5 text-zinc-600" />
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel className="font-normal pb-3">
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-semibold leading-none text-zinc-950">
                      {auth?.user?.github_login || "Local User"}
                    </p>
                    <p className="text-xs leading-none text-zinc-500">
                      {auth?.user?.github_login ? `@${auth.user.github_login}` : "Signed in locally"}
                    </p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />

                {/* Tenants Dropdown */}
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Building2 className="mr-2 size-4 text-zinc-500" />
                    <span>Workspace: {auth?.tenants?.find(t => t.id === auth?.selected_tenant_id)?.name || "Select"}</span>
                  </DropdownMenuSubTrigger>
                  <DropdownMenuPortal>
                    <DropdownMenuSubContent className="w-48">
                      {(auth?.tenants || []).map((tenant) => (
                        <DropdownMenuItem
                          key={tenant.id}
                          onClick={() => void selectTenant(String(tenant.id))}
                          className="flex items-center justify-between cursor-pointer"
                        >
                          {tenant.name || tenant.slug}
                          {auth?.selected_tenant_id === tenant.id && <Check className="size-4 ml-2 text-zinc-950" />}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuSubContent>
                  </DropdownMenuPortal>
                </DropdownMenuSub>

                {/* API Limit */}
                <DropdownMenuItem disabled className="opacity-100">
                  <Server className="mr-2 size-4 text-zinc-500" />
                  <span className="flex-1">API Requests</span>
                  <span className={cn(
                    "text-xs font-medium",
                    (rateLimit?.resources?.core?.remaining ?? rateLimit?.remaining ?? 0) > 0 ? "text-emerald-600" : "text-red-600"
                  )}>
                    {formatNumber(rateLimit?.resources?.core?.remaining ?? rateLimit?.remaining ?? 0)}/
                    {formatNumber(rateLimit?.resources?.core?.limit ?? rateLimit?.limit ?? 0)}
                  </span>
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem className="cursor-pointer">
                  <User className="mr-2 size-4 text-zinc-500" />
                  <span>Your profile</span>
                </DropdownMenuItem>

                <DropdownMenuItem className="cursor-pointer">
                  <Settings className="mr-2 size-4 text-zinc-500" />
                  <span>Settings</span>
                </DropdownMenuItem>

                <DropdownMenuSeparator />

                <DropdownMenuItem onClick={() => void logout()} className="cursor-pointer">
                  <LogOut className="mr-2 size-4 text-red-600" />
                  <span className="text-red-600 font-medium">Sign out</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <div className="flex flex-col lg:flex-row items-stretch min-h-[calc(100vh-80px)]">
        <aside className={`sticky top-20 h-[calc(100vh-80px)] overflow-y-auto border-r border-zinc-200 bg-white p-4 transition-all duration-300 shrink-0 z-20 ${isSidebarExpanded ? "w-full lg:w-[280px]" : "w-full lg:w-[80px]"}`}>
          <div className={`mb-5 rounded-lg border border-zinc-200 ${isSidebarExpanded ? "p-4" : "p-2"}`}>
            <div className={`flex items-center ${isSidebarExpanded ? "justify-between" : "justify-center"} mb-3`}>
              {isSidebarExpanded && <div className="text-xs font-semibold uppercase tracking-wide text-blue-600">Workspace</div>}
              <Button variant="ghost" size="icon" onClick={() => setIsSidebarExpanded(!isSidebarExpanded)} className="size-6 text-zinc-500 hover:text-zinc-900" title={isSidebarExpanded ? "Collapse Sidebar" : "Expand Sidebar"}>
                {isSidebarExpanded ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
              </Button>
            </div>
            <nav className="space-y-1">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.key}
                    onClick={() => openModule(tab.key)}
                    title={tab.label}
                    className={`flex items-center gap-3 rounded-md py-2 transition w-full ${isSidebarExpanded ? "px-3 text-left text-sm font-medium" : "justify-center px-0"} ${activeTab === tab.key ? "bg-zinc-900 text-white" : "text-zinc-700 hover:bg-zinc-100"
                      }`}
                  >
                    <Icon className="size-4 shrink-0" />
                    {isSidebarExpanded && <span className="truncate">{tab.label}</span>}
                  </button>
                );
              })}
            </nav>
          </div>

          {isSidebarExpanded && (
            <div className="rounded-lg border border-zinc-200 p-4">
              <div className="flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wide text-blue-600">Recent</div>
                <button className="text-xs font-medium text-blue-600 hover:underline" onClick={() => void loadHistory()}>Refresh</button>
              </div>
              <div className="mt-3 space-y-2">
                {recentHistory.length ? recentHistory.map((item) => (
                  <button key={item.id} className="w-full rounded-md border border-zinc-200 p-3 text-left hover:bg-zinc-50" onClick={() => void openHistory(item)}>
                    <div className="truncate font-mono text-sm font-semibold">{item.repo}</div>
                    <div className="mt-1 text-xs text-zinc-500">{formatDate(item.analyzed_at)}</div>
                  </button>
                )) : <p className="text-sm text-zinc-500">No analyses yet.</p>}
              </div>
            </div>
          )}
        </aside>

        <main className="min-w-0 flex-1 p-6">
          <ModulePageHeader
            module={activeModule}
            repo={activeRepo}
          />

          <section className="mb-5 rounded-lg border border-zinc-200 bg-white p-4">
            <div className="grid w-full grid-cols-2 rounded-lg border border-zinc-200 p-1">
              <button className={`rounded-md px-4 py-2.5 text-sm font-semibold transition-colors ${mode === "single" ? "bg-zinc-900 text-white shadow" : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"}`} onClick={() => setMode("single")}>Single Analysis</button>
              <button className={`rounded-md px-4 py-2.5 text-sm font-semibold transition-colors ${mode === "batch" ? "bg-zinc-900 text-white shadow" : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-100"}`} onClick={() => setMode("batch")}>Batch Analysis</button>
            </div>

            {mode === "batch" ? (
              <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                <textarea className="min-h-28 rounded-md border border-zinc-300 p-3 font-mono text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" placeholder={"owner/repo\nvercel/next.js"} value={batchInput} onChange={(event) => setBatchInput(event.target.value)} />
                <div className="flex flex-col gap-2">
                  <input
                    type="file"
                    accept=".txt"
                    id="batch-upload"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        const text = await file.text();
                        setBatchInput((prev) => (prev ? prev + "\n" + text : text));
                        e.target.value = "";
                      }
                    }}
                  />
                  <Button variant="outline" asChild>
                    <label htmlFor="batch-upload" className="cursor-pointer">
                      <Upload className="mr-2 size-4" />
                      Upload .txt
                    </label>
                  </Button>
                  <AnimatedActionButton onClick={() => void runBatchAnalysis()} disabled={batchRunning}>
                    {batchRunning ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Play className="mr-2 size-4" />}
                    Run Batch
                  </AnimatedActionButton>
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm text-zinc-600">Supports <strong>owner/repo</strong>, GitHub URLs, and <strong>.git</strong> URLs.</p>
            )}
          </section>

          {progress.length ? (
            <Card className="mb-5">
              <CardHeader>
                <CardTitle>Analysis stream</CardTitle>
                <CardDescription>Live events from /api/analyze/full and /api/batch/analyze.</CardDescription>
              </CardHeader>
              <CardContent className="max-h-64 overflow-auto rounded-b-lg bg-zinc-950 p-4 font-mono text-xs text-zinc-100">
                {progress.map((line) => (
                  <div key={line.id} className={line.level === "error" ? "text-red-300" : line.level === "done" ? "text-emerald-300" : "text-zinc-200"}>
                    <span className="text-blue-300">{line.module}</span> {line.message}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          <ModuleRouteStrip activeTab={activeTab} onSelect={openModule} />

          {activeTab === "overview" ? <OverviewPanel data={analysis} onOpenModule={openModule} /> : null}
          {activeTab === "cicd" ? <CicdPanel data={analysis} /> : null}
          {activeTab === "deps" ? <DependenciesPanel data={analysis} /> : null}
          {activeTab === "pipeline" ? <PipelineMonitorPanel /> : null}
          {activeTab === "setup" ? <RepoSetupPanelV2 repos={setupRepos} auth={auth} onRefresh={loadSetupRepos} onToast={showToast} /> : null}
          {activeTab === "history" ? <AnalysisHistoryPage history={historyItems} onOpen={openHistory} onDelete={deleteHistory} onClear={clearHistory} onToast={showToast} /> : null}
        </main>
      </div>
      <ToastStack toasts={toasts} onDismiss={(id) => setToasts((items) => items.filter((item) => item.id !== id))} />
    </div>
  );
}
