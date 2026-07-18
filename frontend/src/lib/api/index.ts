// Public API surface. Pages import `{ api, ApiError, <types> }` from "../api";
// this barrel keeps that import path stable while the implementation lives in
// focused modules (types, the http core, and one client per resource).

export * from "./types";
export { ApiError, auth, setUnauthorizedHandler } from "./http";

import { agentApi } from "./resources/agent";
import { authApi } from "./resources/auth";
import { metricsApi } from "./resources/metrics";
import { runsApi } from "./resources/runs";
import { tracesApi } from "./resources/traces";
import { workflowsApi } from "./resources/workflows";

/** The flat client the app calls (`api.listWorkflows()`, `api.chat()`, …),
 *  composed from the per-resource clients. */
export const api = {
  ...authApi,
  ...tracesApi,
  ...workflowsApi,
  ...runsApi,
  ...metricsApi,
  ...agentApi,
};
