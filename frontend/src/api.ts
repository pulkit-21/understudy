// Typed client for the Understudy API. Types mirror the pydantic models in
// backend/app/models. Same-origin in both dev (via Vite proxy) and prod.

export type Action =
  | "navigate" | "click" | "fill" | "select" | "extract" | "assert_text";
export type Risk = "read" | "write" | "commit";

export interface TargetInfo {
  role?: string | null;
  name?: string | null;
  testid?: string | null;
  css?: string | null;
  tag?: string | null;
}

export interface WorkflowStep {
  id: string;
  intent: string;
  action: Action;
  target?: TargetInfo | null;
  value?: string | null;
  url?: string | null;
  extract_key?: string | null;
  risk: Risk;
  requires_approval: boolean;
}

export interface WorkflowParameter {
  key: string;
  description: string;
  example?: string | null;
  required: boolean;
}

export type WorkflowStatusT = "draft" | "published" | "archived";

export interface WorkflowSpec {
  id: string;
  name: string;
  description: string;
  version: number;
  status: WorkflowStatusT;
  tags: string[];
  source_trace_ids: string[];
  parameters: WorkflowParameter[];
  steps: WorkflowStep[];
}

export interface TraceSummary {
  id: string;
  name: string;
  events: number;
  started_at: string;
}

export interface SemanticEvent {
  type: string;
  url: string;
  ts_ms: number;
  target?: TargetInfo | null;
  value?: string | null;
  page_title?: string | null;
}

export interface Trace {
  id: string;
  name: string;
  started_at: string;
  start_url?: string | null;
  events: SemanticEvent[];
}

export interface RunSummary {
  id: string;
  workflow_id: string;
  status: RunStatus;
  created_at: string;
  params: Record<string, string>;
  steps: number;
  batch_id?: string | null;
  cost_usd?: number;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  org_id: string;
}

export interface WorkflowVersion {
  version: number;
  created_at: string;
  name: string;
  steps: number;
}

export interface DashboardData {
  workflows: number;
  run_counts: Record<string, number>;
  total_runs: number;
  pending_approvals: number;
  success_rate: number | null;
  cost_usd: number;
  minutes_saved: number;
  recent: RunSummary[];
}

export type RunStatus =
  | "running" | "awaiting_approval" | "completed" | "rejected" | "failed";

export interface RunEvent {
  ts: string;
  actor: string; // "agent" | "human"
  kind: string;
  step_id?: string | null;
  detail: string;
}

export interface Run {
  id: string;
  workflow_id: string;
  params: Record<string, string>;
  status: RunStatus;
  current_step: number;
  events: RunEvent[];
  extracts: Record<string, string>;
}

// A failed request. For 422 the API returns { detail: [...] }; we keep the
// structured detail so the workflow editor can show validation problems inline.
export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// ---- auth token (persisted; attached to every request) ----------------------
const TOKEN_KEY = "understudy_token";
export const auth = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

// Notify the app to bounce to the login screen when a token goes stale.
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const token = auth.get();
  const res = await fetch(url, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) {
      auth.clear();
      onUnauthorized();
    }
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  // ---- auth ----
  register: (email: string, password: string, name: string) =>
    req<{ token: string; user: AuthUser }>("/api/auth/register", {
      method: "POST", body: JSON.stringify({ email, password, name }),
    }),
  login: (email: string, password: string) =>
    req<{ token: string; user: AuthUser }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  me: () => req<AuthUser>("/api/auth/me"),

  listTraces: () => req<TraceSummary[]>("/api/traces"),
  getTrace: (id: string) => req<Trace>(`/api/traces/${id}`),

  startRecording: (name: string, start_url?: string) =>
    req<{ recording_id: string; name: string; start_url: string }>(
      "/api/recordings/start",
      { method: "POST", body: JSON.stringify({ name, start_url }) },
    ),
  stopRecording: (id: string) =>
    req<{ trace_id: string; name: string; events: number }>(
      `/api/recordings/${id}/stop`,
      { method: "POST" },
    ),

  dashboard: () => req<DashboardData>("/api/dashboard"),

  listRuns: (opts?: { status?: string; batch_id?: string }) => {
    const q = new URLSearchParams(
      Object.entries(opts ?? {}).filter(([, v]) => v) as [string, string][],
    ).toString();
    return req<RunSummary[]>("/api/runs" + (q ? `?${q}` : ""));
  },

  induce: (traceId: string, use_llm = true) =>
    req<{ workflow: WorkflowSpec; induced_by: string; problems: string[] }>(
      `/api/traces/${traceId}/induce`,
      { method: "POST", body: JSON.stringify({ use_llm }) },
    ),

  listWorkflows: (includeArchived = false) =>
    req<WorkflowSpec[]>(
      "/api/workflows" + (includeArchived ? "?include_archived=true" : "")),
  getWorkflow: (id: string) => req<WorkflowSpec>(`/api/workflows/${id}`),
  saveWorkflow: (id: string, spec: WorkflowSpec) =>
    req<WorkflowSpec>(`/api/workflows/${id}`, {
      method: "PUT", body: JSON.stringify(spec),
    }),
  setWorkflowStatus: (id: string, status: WorkflowStatusT) =>
    req<WorkflowSpec>(`/api/workflows/${id}/status`, {
      method: "POST", body: JSON.stringify({ status }),
    }),
  duplicateWorkflow: (id: string) =>
    req<WorkflowSpec>(`/api/workflows/${id}/duplicate`, { method: "POST" }),
  deleteWorkflow: (id: string) =>
    req<void>(`/api/workflows/${id}`, { method: "DELETE" }),
  workflowVersions: (id: string) =>
    req<WorkflowVersion[]>(`/api/workflows/${id}/versions`),
  rollbackWorkflow: (id: string, version: number) =>
    req<WorkflowSpec>(`/api/workflows/${id}/rollback/${version}`, {
      method: "POST",
    }),

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
  approve: (id: string) =>
    req<{ ok: boolean }>(`/api/runs/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    req<{ ok: boolean }>(`/api/runs/${id}/reject`, { method: "POST" }),

  // token in the query because EventSource can't send an auth header
  runEventsUrl: (id: string) =>
    `/api/runs/${id}/events?token=${encodeURIComponent(auth.get() ?? "")}`,
};
