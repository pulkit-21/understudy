import { req } from "../http";
import { AuthUser } from "../types";

export const authApi = {
  register: (email: string, password: string, name: string) =>
    req<{ token: string; user: AuthUser }>("/api/auth/register", {
      method: "POST", body: JSON.stringify({ email, password, name }),
    }),
  login: (email: string, password: string) =>
    req<{ token: string; user: AuthUser }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  me: () => req<AuthUser>("/api/auth/me"),
  team: () => req<{ members: { id: string; email: string; name: string; created_at: string }[]; me: string }>(
    "/api/auth/team"),
};
