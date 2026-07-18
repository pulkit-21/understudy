import { auth, req } from "../http";
import { Run, RunSummary } from "../types";

export const runsApi = {
  listRuns: (opts?: { status?: string; batch_id?: string }) => {
    const q = new URLSearchParams(
      Object.entries(opts ?? {}).filter(([, v]) => v) as [string, string][],
    ).toString();
    return req<RunSummary[]>("/api/runs" + (q ? `?${q}` : ""));
  },
  startRun: (wfId: string, params: Record<string, string>) =>
    req<{ run_id: string }>(`/api/workflows/${wfId}/runs`, {
      method: "POST", body: JSON.stringify({ params }),
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

  // token in the query because EventSource can't send an auth header
  runEventsUrl: (id: string) =>
    `/api/runs/${id}/events?token=${encodeURIComponent(auth.get() ?? "")}`,
};
