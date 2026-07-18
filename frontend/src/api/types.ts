// API types — mirror the pydantic models in backend/app/models and the response
// shapes in backend/app/api. Kept in one module, imported by the resource
// clients and the pages.

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
export type ApprovalModeT = "always_ask" | "auto_below_amount";

export interface ApprovalPolicy {
  mode: ApprovalModeT;
  auto_approve_below: number | null;
  amount_key: string;
}

export interface WorkflowSpec {
  id: string;
  name: string;
  description: string;
  version: number;
  status: WorkflowStatusT;
  tags: string[];
  approval_policy: ApprovalPolicy;
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
  has_replay?: boolean;
}

export type RunStatus =
  | "running" | "awaiting_approval" | "completed" | "rejected" | "failed";

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

export interface AgentStep {
  tool: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface AgentCard {
  type: "run" | "workflow";
  id: string;
  status?: RunStatus;
  params?: Record<string, string>;
  param_keys?: string[];
  workflow_id?: string;
  name?: string;
}

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
  cards?: AgentCard[];
  steps?: AgentStep[];
}

export interface TeamMember {
  id: string; email: string; name: string; created_at: string;
}

export interface AuditEvent {
  run_id: string; workflow_id: string; ts: string;
  actor: string; kind: string; detail: string;
}

export interface UsageEntry {
  kind: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  created_at: string;
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
