import { req } from "../http";
import { Run, RunSummary } from "../types";

export const runsApi = {
  listRuns: (opts?: { status?: string; batch_id?: string }) => {
    const q = new URLSearchParams(
      Object.entries(opts ?? {}).filter(([, v]) => v) as [string, string][],
    ).toString();
    return req<RunSummary[]>("/api/runs" + (q ? `?${q}` : ""));
  },
  startRun: (wfId: string, params: Record<string, string>, dry_run = false) =>
    req<{ run_id: string }>(`/api/workflows/${wfId}/runs`, {
      method: "POST", body: JSON.stringify({ params, dry_run }),
    }),
  startBatch: (wfId: string, param_values: string[], param_key?: string) =>
    req<{ batch_id: string; run_ids: string[]; count: number }>(
      `/api/workflows/${wfId}/batch`, {
        method: "POST", body: JSON.stringify({ param_values, param_key }),
      }),
  getRun: (id: string) => req<Run>(`/api/runs/${id}`),
  retryRun: (id: string) =>
    req<{ run_id: string }>(`/api/runs/${id}/retry`, { method: "POST" }),
  approve: (id: string) =>
    req<{ ok: boolean }>(`/api/runs/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    req<{ ok: boolean }>(`/api/runs/${id}/reject`, { method: "POST" }),

  // SSE: mint a short-lived, run-scoped ticket (bearer-authed POST), then open
  // the stream with it — the 7-day JWT never goes in the URL.
  mintStreamTicket: (id: string) =>
    req<{ ticket: string }>(`/api/runs/${id}/events/ticket`, { method: "POST" }),
  runEventsUrl: (id: string, ticket: string) =>
    `/api/runs/${id}/events?ticket=${encodeURIComponent(ticket)}`,
};
