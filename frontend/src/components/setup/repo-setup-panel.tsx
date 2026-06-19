import {
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
import { apiPost } from "@/lib/api";
import type { AuthStatus, SetupRepository } from "@/types/pipeline";
import {
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  Github,
  KeyRound,
  Loader2,
  LockKeyhole,
  Play,
  RefreshCcw,
  RotateCcw,
  SearchCheck,
  Settings,
  ShieldCheck,
  Trash2,
  Workflow,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

type ToastType = "success" | "error" | "warning" | "info";

type SyncInstallResult = {
  status?: string;
  installations?: Array<{
    synced_repository_count?: number;
    synced_repositories?: number;
    provisioned_repository_count?: number;
    provisioned_repositories?: number;
    errors?: Array<{ stage?: string; message?: string }>;
  }>;
};

export interface RepoSetupPanelProps {
  readonly repos: SetupRepository[];
  readonly auth: AuthStatus | null;
  readonly onRefresh: () => Promise<void>;
  readonly onToast: (type: ToastType, message: string) => void;
}

type StepState = {
  label: string;
  ok: boolean;
  value?: string | null;
  description: string;
};

function normalizeRepoSlug(value: string) {
  const slug = String(value || "").trim().replace(/^(https:\/\/github\.com\/|git@github\.com:)/, "").replace(/\.git$/, "");
  const [owner, repo] = slug.split("/");
  if (!owner || !repo) return "";
  if (!/^[A-Za-z0-9_.-]+$/.test(owner) || !/^[A-Za-z0-9_.-]+$/.test(repo)) return "";
  return `${owner}/${repo}`;
}

function formatDate(value?: string | null) {
  if (!value) return "Pending";
  let parsedValue = value;
  if (parsedValue.includes(" ") && !parsedValue.includes("T")) parsedValue = parsedValue.replace(" ", "T");
  const timePart = parsedValue.split("T")[1];
  if (timePart && !timePart.includes("Z") && !timePart.includes("+") && !timePart.includes("-")) parsedValue += "Z";
  const date = new Date(parsedValue);
  if (Number.isNaN(date.getTime())) return "Configured";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function humanize(value?: string | null) {
  return String(value || "pending").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusTone(status?: string | null) {
  const value = String(status || "").toLowerCase();
  if (["active", "provisioned", "completed", "passed", "success"].includes(value)) return "success" as const;
  if (["failed", "error", "blocked"].includes(value)) return "error" as const;
  if (["pending", "pending_pull_request", "dry_run", "needs_attention", "discovered", "setup_pr_open", "cleanup_pr_open"].includes(value)) return "warning" as const;
  if (["ignored", "removed", "deprovisioned", "deprovisioning"].includes(value)) return "info" as const;
  return "neutral" as const;
}

function buildSyncMessage(result: SyncInstallResult) {
  const installations = result.installations || [];
  const synced = installations.reduce((total, item) => total + Number(item.synced_repository_count ?? item.synced_repositories ?? 0), 0);
  const provisioned = installations.reduce((total, item) => total + Number(item.provisioned_repository_count ?? item.provisioned_repositories ?? 0), 0);
  const errors = installations.reduce((total, item) => total + Number(item.errors?.length || 0), 0);
  if (errors > 0) return `Repositories synced with ${errors} warning${errors === 1 ? "" : "s"}.`;
  if (synced || provisioned) return `Repositories synced. ${synced} repo${synced === 1 ? "" : "s"} checked, ${provisioned} configured.`;
  return "Repositories synced successfully.";
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

function repoSteps(repo: SetupRepository): StepState[] {
  return [
    {
      label: "Workflow",
      ok: Boolean(repo.workflow_installed_at),
      value: repo.workflow_installed_at,
      description: ".github/workflows/company-quality-pipeline.yml exists",
    },
    {
      label: "Secrets",
      ok: Boolean(repo.secrets_configured_at),
      value: repo.secrets_configured_at,
      description: "DASHBOARD_URL and repo-scoped DASHBOARD_API_KEY are installed",
    },
    {
      label: "Ruleset",
      ok: Boolean(repo.ruleset_configured_at),
      value: repo.ruleset_configured_at,
      description: "quality-gate and compiler-check are required status checks",
    },
    {
      label: "API key",
      ok: Boolean(repo.api_key_prefix),
      value: repo.api_key_prefix,
      description: "Repo-scoped report token exists in dashboard database",
    },
  ];
}

function repoReady(repo: SetupRepository) {
  return repo.setup_status === "active" && repoSteps(repo).every((step) => step.ok);
}

function repoNeedsConfigure(repo: SetupRepository) {
  return !repoReady(repo) && !["ignored", "removed", "deprovisioned", "deprovisioning", "cleanup_pr_open"].includes(String(repo.setup_status || ""));
}

function repoFixes(repo: SetupRepository) {
  const fixes: string[] = [];
  for (const blocker of repo.provisioning_blockers || []) fixes.push(blocker);
  if (repo.last_setup_error) fixes.push(repo.last_setup_error);
  if (repo.setup_pr_url) fixes.push("GitHub repository rules required a setup pull request. Open and merge the setup PR, then verify again.");
  if (!repo.workflow_installed_at) fixes.push("Workflow is missing. Click Configure to install it, or merge the setup PR if one was created.");
  if (!repo.secrets_configured_at) fixes.push("GitHub Actions secrets are missing. Click Configure so the app can install DASHBOARD_URL and DASHBOARD_API_KEY.");
  if (!repo.ruleset_configured_at) fixes.push("Required-check ruleset is missing. Click Configure so merges require quality-gate and compiler-check.");
  if (!repo.api_key_prefix) fixes.push("Repo API key is missing. Click Configure to generate the repo-scoped dashboard token.");
  return Array.from(new Set(fixes));
}

function StepChecklist({ repo }: Readonly<{ repo: SetupRepository }>) {
  return (
    <div className="grid gap-2 md:grid-cols-4">
      {repoSteps(repo).map((step) => (
        <div key={step.label} className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-zinc-950">{step.label}</span>
            {step.ok ? (
              <CheckCircle2 className="size-4 text-emerald-600" />
            ) : (
              <AlertCircle className="size-4 text-amber-600" />
            )}
          </div>
          <p className="mt-1 text-xs leading-5 text-zinc-600">{step.description}</p>
          <p className="mt-2 font-mono text-xs text-zinc-500">{step.label === "API key" ? step.value || "Pending" : formatDate(step.value)}</p>
        </div>
      ))}
    </div>
  );
}

function RepoSetupCard({
  repo,
  busy,
  selected,
  onConfigure,
  onVerify,
  onSelect,
  onIgnore,
  onRestore,
  onDeprovision,
  onOpenFix,
}: Readonly<{
  repo: SetupRepository;
  busy: boolean;
  selected: boolean;
  onConfigure: () => void;
  onVerify: () => void;
  onSelect: () => void;
  onIgnore: () => void;
  onRestore: () => void;
  onDeprovision: () => void;
  onOpenFix: () => void;
}>) {
  const ready = repoReady(repo);
  const fixes = repoFixes(repo);
  const needsConfigure = repoNeedsConfigure(repo);
  const status = String(repo.setup_status || "");
  const isPaused = ["ignored", "deprovisioned", "removed", "cleanup_pr_open", "deprovisioning"].includes(status);

  return (
    <Card className={selected ? "ring-2 ring-blue-500/30" : undefined}>
      <CardHeader>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="flex min-w-0 gap-3">
            <input
              type="checkbox"
              aria-label={`Select ${repo.full_name}`}
              checked={selected}
              onChange={onSelect}
              className="mt-1 size-4 rounded border-zinc-300"
            />
            <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill tone={ready ? "success" : statusTone(repo.setup_status)} label={ready ? "Ready" : humanize(repo.setup_status)} />
              {repo.default_branch ? <Pill className="border-zinc-200 bg-zinc-50 font-mono text-zinc-700">{repo.default_branch}</Pill> : null}
              {repo.last_verified_at ? <Pill className="border-zinc-200 bg-zinc-50 text-zinc-700">Verified {formatDate(repo.last_verified_at)}</Pill> : null}
            </div>
            <CardTitle className="mt-3 break-all font-mono text-lg">{repo.full_name}</CardTitle>
            <CardDescription className="mt-1">
              {ready ? "Workflow, secrets, ruleset, and repo-scoped report key are ready." : null}
              {!ready && status === "ignored" ? "This repository is ignored and will not be configured until restored." : null}
              {!ready && status === "deprovisioned" ? "Arya setup was removed from this repository. Restore it before configuring again." : null}
              {!ready && status === "cleanup_pr_open" ? "A cleanup pull request is open. Merge it to complete undo setup." : null}
              {!ready && !isPaused ? "This repository still needs one or more setup checks before enforcement is fully active." : null}
            </CardDescription>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {repo.setup_pr_url ? (
              <Button asChild variant="outline" size="sm">
                <a href={repo.setup_pr_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-2 size-4" />
                  Setup PR
                </a>
              </Button>
            ) : null}
            {repo.cleanup_pr_url ? (
              <Button asChild variant="outline" size="sm">
                <a href={repo.cleanup_pr_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-2 size-4" />
                  Cleanup PR
                </a>
              </Button>
            ) : null}
            {fixes.length ? (
              <Button variant="outline" size="sm" onClick={onOpenFix}>
                <AlertCircle className="mr-2 size-4" />
                Fix details
              </Button>
            ) : null}
            {needsConfigure ? (
              <Button size="sm" onClick={onConfigure} disabled={busy}>
                {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Play className="mr-2 size-4" />}
                Configure
              </Button>
            ) : null}
            {status === "ignored" || status === "deprovisioned" || status === "removed" ? (
              <Button variant="outline" size="sm" onClick={onRestore} disabled={busy}>
                {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RotateCcw className="mr-2 size-4" />}
                Restore
              </Button>
            ) : (
              <Button variant="outline" size="sm" onClick={onIgnore} disabled={busy || status === "cleanup_pr_open" || status === "deprovisioning"}>
                Ignore
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={onDeprovision} disabled={busy || status === "deprovisioned" || status === "deprovisioning"}>
              {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Trash2 className="mr-2 size-4" />}
              Undo setup
            </Button>
            <Button variant="outline" size="sm" onClick={onVerify} disabled={busy || status === "ignored" || status === "deprovisioned"}>
              {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : <SearchCheck className="mr-2 size-4" />}
              Verify
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <StepChecklist repo={repo} />
      </CardContent>
    </Card>
  );
}

export function RepoSetupPanel({
  repos,
  auth,
  onRefresh,
  onToast,
}: RepoSetupPanelProps) {
  const [repoInput, setRepoInput] = useState("");
  const [busyRepo, setBusyRepo] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [selectedRepo, setSelectedRepo] = useState<SetupRepository | null>(null);
  const [selectedRepoIds, setSelectedRepoIds] = useState<Set<number>>(new Set());

  const selectedTenant = auth?.tenants?.find((tenant) => String(tenant.id) === String(auth?.selected_tenant_id));
  const activeCount = repos.filter(repoReady).length;
  const attentionCount = repos.filter((repo) => !repoReady(repo)).length;
  const setupPrCount = repos.filter((repo) => repo.setup_pr_url).length;
  const selectedCount = selectedRepoIds.size;

  const sortedRepos = useMemo(() => {
    return [...repos].sort((a, b) => {
      if (repoReady(a) !== repoReady(b)) return repoReady(a) ? 1 : -1;
      return a.full_name.localeCompare(b.full_name);
    });
  }, [repos]);

  function toggleRepo(repoId: number) {
    setSelectedRepoIds((current) => {
      const next = new Set(current);
      if (next.has(repoId)) next.delete(repoId);
      else next.add(repoId);
      return next;
    });
  }

  function toggleAllVisible(checked: boolean) {
    setSelectedRepoIds(checked ? new Set(sortedRepos.map((repo) => repo.id)) : new Set());
  }

  async function syncRepos() {
    setSyncing(true);
    try {
      const result = await apiPost<SyncInstallResult>("/api/setup/sync-installed-repositories", {});
      onToast("success", buildSyncMessage(result));
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, "Repository sync failed. Please retry after a few seconds."));
    } finally {
      setSyncing(false);
    }
  }

  async function configure(repo: SetupRepository) {
    setBusyRepo(repo.id);
    try {
      const result = await apiPost<any>(`/api/setup/repositories/${repo.id}/provision`, {});
      if (result.status === "pending_pull_request") {
        onToast("warning", "Setup pull request created. Merge it, then run Verify.");
      } else {
        onToast("success", `${repo.full_name} configured.`);
      }
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, "Provisioning failed. Check Fix details for the exact setup blocker."));
    } finally {
      setBusyRepo(null);
    }
  }

  async function verify(repo: SetupRepository) {
    setBusyRepo(repo.id);
    try {
      const result = await apiPost<any>(`/api/setup/repositories/${repo.id}/verify`, {});
      const ready = Boolean(result?.verification?.ready);
      onToast(ready ? "success" : "warning", ready ? `${repo.full_name} is ready.` : `${repo.full_name} still needs attention.`);
      await onRefresh();
    } catch (error) {
      onToast("error", safeUserMessage(error, "Verification failed. Confirm GitHub App permissions and repository access."));
    } finally {
      setBusyRepo(null);
    }
  }

  async function repoAction(repo: SetupRepository, action: "ignore" | "restore" | "deprovision") {
    const labels = { ignore: "ignored", restore: "restored", deprovision: "deprovisioned" };
    if (action === "deprovision") {
      const confirmed = window.confirm(
        `Undo Arya setup for ${repo.full_name}?\n\nThis attempts to remove the workflow, repository secrets, and ruleset where GitHub permits it. Pipeline history remains in the dashboard.`
      );
      if (!confirmed) return;
    }

    setBusyRepo(repo.id);
    try {
      const result = await apiPost<any>(`/api/setup/repositories/${repo.id}/${action}`, {});
      const prUrl = result?.repo?.cleanup_pr_url || result?.result?.workflow_removal?.pull_request_url;
      if (action === "deprovision" && prUrl) {
        onToast("warning", `Cleanup PR created for ${repo.full_name}. Merge it to complete undo setup.`);
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
        `Undo Arya setup for ${selectedCount} selected repo${selectedCount === 1 ? "" : "s"}?\n\nThis attempts to remove workflows, repository secrets, and rulesets where GitHub permits it. Pipeline history remains in the dashboard.`
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
      onToast("success", `${repo} registered for monitoring.`);
      await onRefresh();
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "Repository registration failed.");
    } finally {
      setRegistering(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <CardDescription className="font-semibold uppercase tracking-wide text-blue-600">
                Autonomous onboarding
              </CardDescription>
              <CardTitle className="mt-2 text-2xl">Repo Setup</CardTitle>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600">
                Client work should stop at GitHub App install and repository selection. This page verifies that the backend handled workflow, secrets, and required-check rulesets.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {auth?.github_app_install_url ? (
                <Button asChild>
                  <a href={auth.github_app_install_url} target="_blank" rel="noreferrer">
                    <Github className="mr-2 size-4" />
                    Install GitHub App
                  </a>
                </Button>
              ) : (
                <Button disabled>
                  <Github className="mr-2 size-4" />
                  GitHub App unavailable
                </Button>
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

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Installed account" value={selectedTenant?.name || auth?.user?.github_login || "Not connected"} hint="Current tenant/workspace" tone={selectedTenant ? "success" : "warning"} icon={Github} />
        <MetricCard label="Monitored repos" value={repos.length} hint="Synced from GitHub App installation" tone="neutral" icon={Workflow} />
        <MetricCard label="Ready" value={activeCount} hint="Workflow, secrets, ruleset, and API key verified" tone={activeCount ? "success" : "neutral"} icon={ShieldCheck} />
        <MetricCard label="Needs attention" value={attentionCount + setupPrCount} hint={`${setupPrCount} setup PR${setupPrCount === 1 ? "" : "s"} open`} tone={attentionCount ? "warning" : "success"} icon={AlertCircle} />
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <SectionHeader
              eyebrow="Repository controls"
              title="Select repos and apply setup actions"
              description="Use this for operator work: configure selected repos, pause monitoring with Ignore, or undo Arya setup from GitHub."
            />
            <div className="flex flex-wrap items-center gap-2">
              <label className="inline-flex items-center gap-2 rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700">
                <input
                  type="checkbox"
                  checked={sortedRepos.length > 0 && selectedRepoIds.size === sortedRepos.length}
                  onChange={(event) => toggleAllVisible(event.currentTarget.checked)}
                />
                Select all
              </label>
              <StatusPill tone={selectedCount ? "info" : "neutral"} label={`${selectedCount} selected`} />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => void bulkAction("configure")} disabled={!selectedCount || syncing}>
              {syncing ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Play className="mr-2 size-4" />}
              Configure selected
            </Button>
            <Button variant="outline" onClick={() => void bulkAction("ignore")} disabled={!selectedCount || syncing}>
              Ignore selected
            </Button>
            <Button variant="outline" onClick={() => void bulkAction("deprovision")} disabled={!selectedCount || syncing}>
              {syncing ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Trash2 className="mr-2 size-4" />}
              Undo setup for selected
            </Button>
            {selectedCount ? (
              <Button variant="ghost" onClick={() => setSelectedRepoIds(new Set())} disabled={syncing}>
                Clear selection
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeader
            eyebrow="Setup flow"
            title="What the client should experience"
            description="After install, the backend syncs selected repositories and configures enforcement. Buttons appear only for retry, verification, or setup PR handoff."
          />
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-4">
            {[
              ["Install App", "Client authorizes once", Github],
              ["Sync Repos", "Backend imports selected repositories", RefreshCcw],
              ["Provision", "Workflow, secrets, and ruleset are applied", Settings],
              ["Verify", "Dashboard checks GitHub live status", SearchCheck],
            ].map(([title, description, Icon]) => {
              const Component = Icon as typeof Github;
              return (
                <div key={String(title)} className="rounded-lg border border-zinc-200 bg-zinc-50 p-4">
                  <Component className="mb-3 size-5 text-zinc-600" />
                  <h3 className="text-sm font-semibold text-zinc-950">{String(title)}</h3>
                  <p className="mt-1 text-xs leading-5 text-zinc-600">{String(description)}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {sortedRepos.length ? (
        <div className="space-y-3">
          {sortedRepos.map((repo) => (
            <RepoSetupCard
              key={repo.id}
              repo={repo}
              busy={busyRepo === repo.id}
              selected={selectedRepoIds.has(repo.id)}
              onConfigure={() => void configure(repo)}
              onVerify={() => void verify(repo)}
              onSelect={() => toggleRepo(repo.id)}
              onIgnore={() => void repoAction(repo, "ignore")}
              onRestore={() => void repoAction(repo, "restore")}
              onDeprovision={() => void repoAction(repo, "deprovision")}
              onOpenFix={() => setSelectedRepo(repo)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Github}
          title="No monitored repositories yet"
          message="Install the GitHub App, select repositories, then sync installed repositories. The backend will register them under this tenant."
          action={auth?.github_app_install_url ? (
            <Button asChild>
              <a href={auth.github_app_install_url} target="_blank" rel="noreferrer">
                Install GitHub App
              </a>
            </Button>
          ) : undefined}
        />
      )}

      <Card>
        <CardHeader>
          <SectionHeader
            eyebrow="Fallback"
            title="Manual repo registration"
            description="Use only for local demos or when a repo was not returned by GitHub App sync. Production onboarding should use GitHub App install."
          />
        </CardHeader>
        <CardContent>
          <form onSubmit={registerRepo} className="grid gap-3 md:grid-cols-[1fr_auto]">
            <input
              className="repo-input min-w-0"
              placeholder="owner/repo"
              value={repoInput}
              onChange={(event) => setRepoInput(event.target.value)}
            />
            <Button type="submit" variant="outline" disabled={registering}>
              {registering ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
              Register fallback
            </Button>
          </form>
        </CardContent>
      </Card>

      <DetailDrawer
        open={Boolean(selectedRepo)}
        title={selectedRepo?.full_name || "Setup details"}
        description="Exact blockers and next fixes for this repository."
        onClose={() => setSelectedRepo(null)}
      >
        {selectedRepo ? (
          <div className="space-y-5">
            <Card>
              <CardHeader>
                <SectionHeader
                  eyebrow="Status"
                  title={repoReady(selectedRepo) ? "Repository is ready" : "Repository needs attention"}
                  description="This checklist is based on the current dashboard record. Run Verify to refresh it from GitHub."
                  action={<StatusPill tone={repoReady(selectedRepo) ? "success" : "warning"} label={humanize(selectedRepo.setup_status)} />}
                />
              </CardHeader>
              <CardContent>
                <StepChecklist repo={selectedRepo} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <SectionHeader
                  eyebrow="Fix"
                  title="Exact next steps"
                  description="These are client-safe actions. Admin-only platform configuration blockers are named explicitly."
                />
              </CardHeader>
              <CardContent className="space-y-3">
                {repoFixes(selectedRepo).map((fix, index) => (
                  <div key={`${fix}-${index}`} className="flex gap-3 rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                    <p className="text-sm leading-6 text-zinc-700">{fix}</p>
                  </div>
                ))}
                {repoFixes(selectedRepo).length === 0 ? (
                  <div className="flex gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
                    <p className="text-sm leading-6 text-emerald-800">No setup blockers detected.</p>
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <SectionHeader eyebrow="Security" title="Secret handling" />
              </CardHeader>
              <CardContent className="space-y-2 text-sm leading-6 text-zinc-600">
                <p><LockKeyhole className="mr-2 inline size-4" /> GitHub secret values are never displayed. The dashboard only verifies required secret names.</p>
                <p><KeyRound className="mr-2 inline size-4" /> Repo API key prefix is safe to show; the raw key is stored only as a GitHub Actions secret.</p>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </DetailDrawer>
    </div>
  );
}
