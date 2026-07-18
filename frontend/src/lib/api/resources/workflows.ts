import { req } from "../http";
import { WorkflowSpec, WorkflowStatusT, WorkflowVersion } from "../types";

export const workflowsApi = {
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
};
