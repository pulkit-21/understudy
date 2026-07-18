import { req } from "../http";

export interface Schedule {
  id: string;
  workflow_id: string;
  params: Record<string, string>;
  interval_minutes: number;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  next_run_at: string;
}

export const schedulesApi = {
  listSchedules: () => req<Schedule[]>("/api/schedules"),
  createSchedule: (workflow_id: string, params: Record<string, string>,
                   interval_minutes: number) =>
    req<Schedule>("/api/schedules", {
      method: "POST",
      body: JSON.stringify({ workflow_id, params, interval_minutes }),
    }),
  toggleSchedule: (id: string, enabled: boolean) =>
    req<{ ok: boolean }>(`/api/schedules/${id}/toggle`, {
      method: "POST", body: JSON.stringify({ enabled }),
    }),
  deleteSchedule: (id: string) =>
    req<void>(`/api/schedules/${id}`, { method: "DELETE" }),
};
