import { req } from "../http";
import { AuditEvent, DashboardData, UsageEntry } from "../types";

export const metricsApi = {
  dashboard: () => req<DashboardData>("/api/dashboard"),
  usage: () => req<{ total_usd: number; entries: UsageEntry[] }>("/api/usage"),
  auditLog: () => req<{ events: AuditEvent[] }>("/api/audit"),
};
