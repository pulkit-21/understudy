import { useEffect, useState } from "react";
import { ApiError } from "../api";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** Re-run the fetch (e.g. after a mutation). */
  reload: () => void;
  /** Optimistically patch the local data without a refetch. */
  set: (updater: (prev: T | null) => T | null) => void;
}

/**
 * Data-fetching hook: runs `fn` on mount and whenever `deps` change, tracking
 * loading/error state and exposing `reload`. Replaces the useState+useEffect+
 * try/catch boilerplate every list page used to repeat, and standardizes how
 * ApiError is surfaced. Stale responses are ignored (the `alive` guard) so a
 * fast dependency change can't clobber newer data.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fn()
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? String(e.detail) : String(e));
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return {
    data, error, loading,
    reload: () => setNonce((n) => n + 1),
    set: (updater) => setData((prev) => updater(prev)),
  };
}
