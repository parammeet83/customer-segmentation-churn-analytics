import { useCallback, useEffect, useState } from "react";

// Production builds point at the separately deployed API; development uses the
// Vite proxy (same origin). No credentials are ever sent from the browser.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>, signal?: AbortSignal): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== "") qs.set(k, String(v));
  const url = `${BASE}/api/v1${path}${qs.size ? `?${qs}` : ""}`;
  const res = await fetch(url, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export interface ApiState<T> {
  data: T | null;
  error: ApiError | Error | null;
  loading: boolean;
  retry: () => void;
}

/** Fetch hook with loading / error / retry. Never substitutes placeholder data. */
export function useApi<T>(path: string | null, params?: Record<string, string | number | boolean | undefined>): ApiState<T> {
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify(params ?? {});
  const reqKey = path === null ? null : `${path}|${key}|${attempt}`;
  // The latest settled request; loading is derived by comparing keys, so the
  // effect never sets state synchronously.
  const [settled, setSettled] = useState<{ key: string; data: T | null; error: Error | null } | null>(null);

  useEffect(() => {
    if (path === null || reqKey === null) return;
    const ctrl = new AbortController();
    apiGet<T>(path, JSON.parse(key), ctrl.signal)
      .then((d) => {
        setSettled({ key: reqKey, data: d, error: null });
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setSettled({ key: reqKey, data: null, error: e instanceof Error ? e : new Error(String(e)) });
      });
    return () => ctrl.abort();
  }, [path, key, reqKey]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  const current = settled && settled.key === reqKey ? settled : null;
  return {
    // While a new request is in flight the previous successful data stays visible.
    data: current ? current.data : (settled?.data ?? null),
    error: current?.error ?? null,
    loading: reqKey !== null && current === null,
    retry,
  };
}
