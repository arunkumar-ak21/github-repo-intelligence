import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Pill, PillIndicator } from "@/components/ui/pill";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  Info,
  PanelRightOpen,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

export type StatusTone = "success" | "warning" | "error" | "info" | "neutral";

export interface PageHeaderProps {
  readonly eyebrow?: string;
  readonly title: string;
  readonly description?: string;
  readonly repo?: string;
  readonly meta?: ReactNode;
  readonly footer?: ReactNode;
  readonly action?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, repo, meta, footer, action }: PageHeaderProps) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {eyebrow ? <StatusPill tone="info" label={eyebrow} /> : null}
            {repo ? <Pill className="border-zinc-200 bg-white font-mono text-zinc-700">{repo}</Pill> : null}
            {meta}
          </div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-zinc-950 md:text-4xl">{title}</h1>
          {description ? <p className="mt-3 max-w-4xl text-base leading-7 text-zinc-600">{description}</p> : null}
          {footer ? <div className="mt-3">{footer}</div> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
    </section>
  );
}

export interface SectionHeaderProps {
  readonly eyebrow?: string;
  readonly title: string;
  readonly description?: string;
  readonly action?: ReactNode;
  readonly className?: string;
}

export function SectionHeader({ eyebrow, title, description, action, className }: SectionHeaderProps) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between", className)}>
      <div>
        {eyebrow ? <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">{eyebrow}</p> : null}
        <h2 className="mt-1 text-lg font-semibold text-zinc-950">{title}</h2>
        {description ? <p className="mt-1 text-sm leading-6 text-zinc-600">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export interface MetricCardProps {
  readonly label: string;
  readonly value: ReactNode;
  readonly hint?: string;
  readonly icon?: LucideIcon;
  readonly tone?: StatusTone;
}

export function MetricCard({ label, value, hint, icon: Icon, tone = "neutral" }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardDescription>{label}</CardDescription>
            <CardTitle className="mt-2 text-2xl">{value}</CardTitle>
          </div>
          {Icon ? (
            <span className={cn("grid size-9 place-items-center rounded-md border", toneClasses[tone].icon)}>
              <Icon className="size-4" />
            </span>
          ) : null}
        </div>
        {hint ? <p className="text-xs leading-5 text-zinc-500">{hint}</p> : null}
      </CardHeader>
    </Card>
  );
}

const toneClasses: Record<StatusTone, { pill: string; icon: string; dot: "success" | "warning" | "error" | "info" }> = {
  success: {
    pill: "border-emerald-200 bg-emerald-50 text-emerald-700",
    icon: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dot: "success",
  },
  warning: {
    pill: "border-amber-200 bg-amber-50 text-amber-700",
    icon: "border-amber-200 bg-amber-50 text-amber-700",
    dot: "warning",
  },
  error: {
    pill: "border-rose-200 bg-rose-50 text-rose-700",
    icon: "border-rose-200 bg-rose-50 text-rose-700",
    dot: "error",
  },
  info: {
    pill: "border-blue-200 bg-blue-50 text-blue-700",
    icon: "border-blue-200 bg-blue-50 text-blue-700",
    dot: "info",
  },
  neutral: {
    pill: "border-zinc-200 bg-zinc-50 text-zinc-700",
    icon: "border-zinc-200 bg-zinc-50 text-zinc-700",
    dot: "info",
  },
};

export interface StatusPillProps {
  readonly label: ReactNode;
  readonly tone?: StatusTone;
  readonly pulse?: boolean;
  readonly className?: string;
}

export function StatusPill({ label, tone = "neutral", pulse = false, className }: StatusPillProps) {
  return (
    <Pill className={cn(toneClasses[tone].pill, className)}>
      <PillIndicator variant={toneClasses[tone].dot} pulse={pulse} />
      {label}
    </Pill>
  );
}

export interface DataTableColumn<T> {
  readonly key: string;
  readonly header: ReactNode;
  readonly className?: string;
  readonly render: (row: T, index: number) => ReactNode;
}

export interface DataTableProps<T> {
  readonly columns: DataTableColumn<T>[];
  readonly rows: T[];
  readonly getRowKey?: (row: T, index: number) => string;
  readonly empty?: ReactNode;
  readonly className?: string;
}

export function DataTable<T>({ columns, rows, getRowKey, empty, className }: DataTableProps<T>) {
  return (
    <div className={cn("overflow-x-auto rounded-lg border border-zinc-200 bg-white", className)}>
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-600">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={cn("px-4 py-3", column.className)}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row, index) => (
            <tr key={getRowKey ? getRowKey(row, index) : String(index)} className="border-b border-zinc-100 last:border-0 hover:bg-zinc-50/70">
              {columns.map((column) => (
                <td key={column.key} className={cn("px-4 py-3 align-top text-zinc-700", column.className)}>
                  {column.render(row, index)}
                </td>
              ))}
            </tr>
          )) : (
            <tr>
              <td className="px-4 py-8 text-center text-sm text-zinc-500" colSpan={columns.length}>
                {empty || "No data returned."}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export interface FindingCardProps {
  readonly title: string;
  readonly message?: string;
  readonly severity?: string;
  readonly file?: string;
  readonly ruleId?: string;
  readonly recommendation?: string;
  readonly evidence?: ReactNode;
}

export function FindingCard({ title, message, severity, file, ruleId, recommendation, evidence }: FindingCardProps) {
  const tone = severityToTone(severity);
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-zinc-950">{title}</h3>
          <p className="mt-1 truncate font-mono text-xs text-zinc-500">{[ruleId, file].filter(Boolean).join(" - ")}</p>
        </div>
        <StatusPill tone={tone} label={String(severity || "info").toUpperCase()} />
      </div>
      {message ? <p className="mt-3 text-sm leading-6 text-zinc-600">{message}</p> : null}
      {recommendation ? <p className="mt-2 text-sm leading-6 text-zinc-800"><strong>Recommendation:</strong> {recommendation}</p> : null}
      {evidence ? <div className="mt-3">{evidence}</div> : null}
    </div>
  );
}

export interface DetailDrawerProps {
  readonly open: boolean;
  readonly title: string;
  readonly description?: string;
  readonly children: ReactNode;
  readonly onClose: () => void;
}

export function DetailDrawer({ open, title, description, children, onClose }: DetailDrawerProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-zinc-950/30" role="dialog" aria-modal="true">
      <button className="absolute inset-0 cursor-default" aria-label="Close detail drawer" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-2xl flex-col border-l border-zinc-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-zinc-200 p-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">Details</p>
            <h2 className="mt-1 text-xl font-semibold text-zinc-950">{title}</h2>
            {description ? <p className="mt-1 text-sm leading-6 text-zinc-600">{description}</p> : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} title="Close drawer">
            <X className="size-5" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-5">{children}</div>
      </aside>
    </div>
  );
}

export interface EmptyStateProps {
  readonly title: string;
  readonly message?: string;
  readonly icon?: LucideIcon;
  readonly action?: ReactNode;
}

export function EmptyState({ title, message, icon: Icon = Clock3, action }: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center">
      <Icon className="mx-auto mb-3 size-8 text-zinc-400" />
      <h3 className="text-base font-semibold text-zinc-950">{title}</h3>
      {message ? <p className="mx-auto mt-1 max-w-xl text-sm leading-6 text-zinc-600">{message}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function severityToTone(severity?: string | null): StatusTone {
  const value = String(severity || "").toLowerCase();
  if (value.includes("critical") || value.includes("high") || value.includes("fail") || value.includes("error")) return "error";
  if (value.includes("medium") || value.includes("moderate") || value.includes("warn")) return "warning";
  if (value.includes("pass") || value.includes("success") || value.includes("ok")) return "success";
  if (value.includes("low") || value.includes("info")) return "info";
  return "neutral";
}

export function statusIcon(tone: StatusTone) {
  if (tone === "success") return CheckCircle2;
  if (tone === "warning") return AlertTriangle;
  if (tone === "error") return AlertTriangle;
  if (tone === "info") return Info;
  return Circle;
}

export function DrawerButton({ onClick, children = "Open details" }: Readonly<{ onClick: () => void; children?: ReactNode }>) {
  return (
    <Button variant="outline" size="sm" onClick={onClick} className="gap-2">
      <PanelRightOpen className="size-4" />
      {children}
    </Button>
  );
}
