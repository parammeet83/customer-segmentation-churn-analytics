import { useId, useState, type ReactNode } from "react";
import type { ApiState } from "../lib/api";

export function PageHeader({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <header className="mb-6 sm:mb-8">
      <h1 className="text-[2rem] leading-[1.05] font-extrabold tracking-tight text-ink sm:text-5xl">{title}</h1>
      <p className="mt-3 max-w-3xl text-base text-gold sm:text-lg">{subtitle}</p>
      {children}
    </header>
  );
}

/** Gold numbered circles, as used for the analytical steps in the reference image. */
export function Steps({ items }: { items: ReactNode[] }) {
  return (
    <ol className="divide-y divide-dashed divide-line">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-3 py-2.5">
          <span
            aria-hidden="true"
            className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-gold text-sm font-bold text-gold"
          >
            {i + 1}
          </span>
          <span className="text-ink-2">
            <span className="sr-only">Step {i + 1}: </span>
            {item}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The strong gold business-takeaway banner. */
export function Banner({ label = "Business takeaway", children }: { label?: string; children: ReactNode }) {
  return (
    <aside role="note" aria-label={label} className="rounded-md bg-gold px-5 py-4 text-gold-ink shadow-[0_8px_30px_-12px_rgba(245,197,66,0.6)]">
      <p className="text-[15px] leading-snug font-bold sm:text-base">
        <span className="mr-1">{label}:</span>
        <span className="font-semibold">{children}</span>
      </p>
    </aside>
  );
}

export function Panel({
  title,
  subtitle,
  children,
  table,
  className = "",
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  table?: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  return (
    <section aria-labelledby={id} className={`panel min-w-0 p-4 sm:p-5 ${className}`}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 id={id} className="text-base font-bold text-ink sm:text-lg">
            {title}
          </h2>
          {subtitle && <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {table && (
            <button
              type="button"
              onClick={() => setShowTable((s) => !s)}
              aria-pressed={showTable}
              className="rounded-md border border-line px-2.5 py-1 text-xs text-ink-2 hover:border-gold hover:text-gold"
            >
              {showTable ? "Show chart" : "Show table"}
            </button>
          )}
        </div>
      </div>
      {showTable && table ? <div className="overflow-x-auto">{table}</div> : children}
    </section>
  );
}

export function Stat({ label, value, hint, accent = false }: { label: string; value: ReactNode; hint?: ReactNode; accent?: boolean }) {
  return (
    <div className="panel p-4">
      <p className="text-xs font-medium tracking-wide text-ink-3 uppercase">{label}</p>
      <p className={`tabular mt-1.5 text-2xl font-extrabold sm:text-[1.75rem] ${accent ? "text-gold" : "text-ink"}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

export function Loading({ label = "Loading results" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="panel flex min-h-40 items-center justify-center gap-3 p-8 text-ink-3">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-gold border-t-transparent" aria-hidden="true" />
      {label}…
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="panel border-bad/60 p-6">
      <p className="font-bold text-ink">Could not load this data.</p>
      <p className="mt-1 text-sm text-ink-3">{error.message}</p>
      <p className="mt-1 text-sm text-ink-3">No figures are shown rather than showing stale or placeholder numbers.</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-4 rounded-md bg-gold px-4 py-2 text-sm font-bold text-gold-ink hover:bg-gold-soft">
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="panel p-6 text-center text-sm text-ink-3">{children}</div>;
}

/** Renders loading / error / empty states, then children with data. */
export function Async<T>({ state, children, isEmpty }: { state: ApiState<T>; children: (data: T) => ReactNode; isEmpty?: (d: T) => boolean }) {
  if (state.error) return <ErrorState error={state.error} onRetry={state.retry} />;
  if (state.loading && !state.data) return <Loading />;
  if (!state.data) return <Loading />;
  if (isEmpty?.(state.data)) return <Empty>No results match the current selection.</Empty>;
  return <>{children(state.data)}</>;
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "gold" | "bad" | "good" | "warn" }) {
  const tones = {
    neutral: "border-line text-ink-2",
    gold: "border-gold/60 text-gold",
    bad: "border-bad/60 text-bad",
    good: "border-good/60 text-good",
    warn: "border-warn/60 text-warn",
  };
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${tones[tone]}`}>{children}</span>;
}

export function SegmentSwatch({ color, name }: { color: string; name: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
      <span>{name}</span>
    </span>
  );
}

export function DataTable({ columns, rows, caption }: { columns: { key: string; label: string; align?: "left" | "right" }[]; rows: Record<string, ReactNode>[]; caption?: string }) {
  return (
    <div className="max-w-full overflow-x-auto">
    <table className="w-full min-w-[520px] text-left text-sm">
      {caption && <caption className="sr-only">{caption}</caption>}
      <thead>
        <tr className="border-b border-line text-xs text-ink-3 uppercase">
          {columns.map((c) => (
            <th key={c.key} scope="col" className={`px-2 py-2 font-medium ${c.align === "right" ? "text-right" : ""}`}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-line/50 last:border-0">
            {columns.map((c) => (
              <td key={c.key} className={`tabular px-2 py-2 text-ink-2 ${c.align === "right" ? "text-right" : ""}`}>
                {r[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/** Shared Recharts tooltip shell. */
export function TooltipBox({ title, rows }: { title?: ReactNode; rows: [ReactNode, ReactNode][] }) {
  return (
    <div className="rounded-lg border border-line bg-navy-950/95 px-3 py-2 text-xs shadow-xl">
      {title && <p className="mb-1 font-bold text-ink">{title}</p>}
      {rows.map(([k, v], i) => (
        <p key={i} className="flex justify-between gap-4 text-ink-3">
          <span>{k}</span>
          <span className="tabular font-semibold text-ink">{v}</span>
        </p>
      ))}
    </div>
  );
}
