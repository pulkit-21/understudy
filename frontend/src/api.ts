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

export interface WorkflowSpec {
  id: string;
  name: string;
  description: string;
  version: number;
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

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
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

  listRuns: () => req<RunSummary[]>("/api/runs"),

  induce: (traceId: string, use_llm = true) =>
    req<{ workflow: WorkflowSpec; induced_by: string; problems: string[] }>(
      `/api/traces/${traceId}/induce`,
      { method: "POST", body: JSON.stringify({ use_llm }) },
    ),

  listWorkflows: () => req<WorkflowSpec[]>("/api/workflows"),
  getWorkflow: (id: string) => req<WorkflowSpec>(`/api/workflows/${id}`),
  saveWorkflow: (id: string, spec: WorkflowSpec) =>
    req<WorkflowSpec>(`/api/workflows/${id}`, {
      method: "PUT",
      body: JSON.stringify(spec),
    }),

  startRun: (wfId: string, params: Record<string, string>) =>
    req<{ run_id: string }>(`/api/workflows/${wfId}/runs`, {
      method: "POST",
      body: JSON.stringify({ params }),
    }),
  getRun: (id: string) => req<Run>(`/api/runs/${id}`),
  approve: (id: string) =>
    req<{ ok: boolean }>(`/api/runs/${id}/approve`, { method: "POST" }),
  reject: (id: string) =>
    req<{ ok: boolean }>(`/api/runs/${id}/reject`, { method: "POST" }),

  runEventsUrl: (id: string) => `/api/runs/${id}/events`,
};
