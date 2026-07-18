import { req } from "../http";
import { Trace, TraceSummary, WorkflowSpec } from "../types";

export const tracesApi = {
  listTraces: () => req<TraceSummary[]>("/api/traces"),
  getTrace: (id: string) => req<Trace>(`/api/traces/${id}`),
  getReplay: (id: string) => req<{ events: unknown[] }>(`/api/traces/${id}/replay`),

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

  induce: (traceId: string, use_llm = true) =>
    req<{ workflow: WorkflowSpec; induced_by: string; problems: string[] }>(
      `/api/traces/${traceId}/induce`,
      { method: "POST", body: JSON.stringify({ use_llm }) },
    ),

  induceMulti: (trace_ids: string[], use_llm = true) =>
    req<{
      workflow: WorkflowSpec; induced_by: string; problems: string[];
      parameter_report: {
        aligned: boolean; trace_count: number;
        fields: { label: string; values: string[]; varies: boolean; role: string }[];
      };
    }>("/api/induce/multi", {
      method: "POST", body: JSON.stringify({ trace_ids, use_llm }),
    }),
};
