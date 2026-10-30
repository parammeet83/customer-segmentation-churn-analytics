import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { useApi } from "../lib/api";
import { dateOnly } from "../lib/format";
import type { RunInfo } from "../lib/types";

const NAV = [
  { to: "/", label: "Overview", n: 0 },
  { to: "/segments", label: "Customer Segmentation", n: 1 },
  { to: "/segment-profiles", label: "Segment Profiles", n: 1 },
  { to: "/churn-risk", label: "Churn Risk", n: 2 },
  { to: "/explainability", label: "SHAP Explainability", n: 3 },
  { to: "/simulator", label: "Retention Simulator", n: 4 },
  { to: "/model-performance", label: "Model Performance", n: 2 },
  { to: "/methodology", label: "Data & Methodology", n: 0 },
] as const;

function RunBadge() {
  const { data, error } = useApi<RunInfo[]>("/analysis-runs", { limit: 5 });
  if (error) return <p className="text-xs text-bad">API unavailable</p>;
  if (!data) return <p className="text-xs text-ink-3">Checking analysis run…</p>;
  const served = data.find((r) => r.status === "succeeded");
  const latest = data[0];
  return (
    <div className="space-y-1 text-xs text-ink-3">
      {served ? (
        <p>
          Serving run <span className="font-mono text-ink-2">{served.run_id.slice(0, 8)}</span>
          <br />
          scored at {served.scoring_cutoff ? dateOnly(served.scoring_cutoff) : "n/a"}
        </p>
      ) : (
        <p className="text-warn">No successful analysis run yet</p>
      )}
      {latest && served && latest.run_id !== served.run_id && (
        <p className="text-warn">Latest run {latest.status}; showing last successful results.</p>
      )}
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const nav = (
    <nav aria-label="Primary">
      <ul className="space-y-1">
        {NAV.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive ? "bg-navy-700 font-bold text-gold" : "text-ink-2 hover:bg-navy-800 hover:text-ink"
                }`
              }
            >
              <span
                aria-hidden="true"
                className={`inline-flex h-5 w-5 items-center justify-center rounded-full border text-[10px] font-bold ${
                  item.n ? "border-gold/70 text-gold" : "border-line text-ink-3"
                }`}
              >
                {item.n || "·"}
              </span>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );

  return (
    <div className="grid-canvas min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-gold focus:px-3 focus:py-2 focus:text-gold-ink">
        Skip to content
      </a>
      <div className="mx-auto flex max-w-[1500px]">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-navy-950/70 p-5 backdrop-blur lg:flex">
          <Brand />
          <div className="mt-8 flex-1">{nav}</div>
          <RunBadge />
        </aside>

        <div className="min-w-0 flex-1">
          <div className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-navy-950/90 px-4 py-3 backdrop-blur lg:hidden">
            <Brand />
            <button
              type="button"
              aria-expanded={open}
              aria-controls="mobile-nav"
              onClick={() => setOpen((o) => !o)}
              className="rounded-md border border-line px-3 py-1.5 text-sm text-ink-2"
            >
              {open ? "Close" : "Menu"}
            </button>
          </div>
          {open && (
            <div id="mobile-nav" className="border-b border-line bg-navy-950 p-4 lg:hidden">
              {nav}
              <div className="mt-4">
                <RunBadge />
              </div>
            </div>
          )}
          <main id="main" key={loc.pathname} className="px-4 py-6 sm:px-8 sm:py-10">
            <Outlet />
          </main>
          <footer className="border-t border-line px-4 py-6 text-xs text-ink-3 sm:px-8">
            Data: Chen, D. (2012). <em>Online Retail II</em>. UCI Machine Learning Repository,{" "}
            <a className="underline hover:text-gold" href="https://doi.org/10.24432/C5CG6D">
              doi:10.24432/C5CG6D
            </a>{" "}
            (CC BY 4.0). A historical UK online retailer, 2009–2011; not representative of current or other markets. Revenue figures
            are scenario estimates, not observed savings.
          </footer>
        </div>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <NavLink to="/" className="flex items-center gap-2.5" aria-label="CustomerPulse home">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="#10244a" stroke="#1d3a6e" />
        <circle cx="10" cy="12" r="3.2" fill="#e0585e" />
        <circle cx="21" cy="10" r="3.2" fill="#f5c542" />
        <circle cx="16" cy="21" r="3.2" fill="#169c8f" />
      </svg>
      <span className="text-lg font-extrabold tracking-tight text-ink">
        Customer<span className="text-gold">Pulse</span>
      </span>
    </NavLink>
  );
}
