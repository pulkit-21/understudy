// The HTTP core: the persisted auth token, the shared fetch wrapper, and the
// error type. Resource clients build on `req`; nothing else talks to fetch.

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

export async function req<T>(url: string, init?: RequestInit): Promise<T> {
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
