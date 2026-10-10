export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const BASE = `${API_URL}/api/v1`;
const TOKEN_KEY = "nigraan.token";
const USER_KEY = "nigraan.user";

export type Role = "accountant" | "approver" | "owner";
export type User = { id: number; name: string; email: string; role: Role };

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public field?: string) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as User) : null;
}

export function storeSession(token: string, user: User) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

// Requests in flight (drives the top progress bar) and a hook for "something changed on the server".
let inflight = 0;
let writes = 0;
const activityListeners = new Set<() => void>();
const idleWaiters = new Set<() => void>();
const mutationListeners = new Set<(path: string) => void>();
// POSTs that compute or authenticate but change no business data.
const READ_ONLY = ["/auth/login", "/cash/scenarios"];

function setInflight(delta: number) {
  inflight += delta;
  activityListeners.forEach((l) => l());
}
export function subscribeActivity(cb: () => void) {
  activityListeners.add(cb);
  return () => {
    activityListeners.delete(cb);
  };
}
export const getActivity = () => inflight;
/** Resolves once no write is in flight (background prefetches wait, e.g. while a demo reset rebuilds the data). */
export function writesSettled(): Promise<void> {
  return writes === 0 ? Promise.resolve() : new Promise((resolve) => idleWaiters.add(resolve));
}
export const writing = () => writes > 0;
export function onMutation(cb: (path: string) => void) {
  mutationListeners.add(cb);
  return () => {
    mutationListeners.delete(cb);
  };
}

async function request<T>(method: string, path: string, body?: unknown, background = false): Promise<T> {
  const write = method !== "GET" && !READ_ONLY.some((p) => path.startsWith(p));
  setInflight(1);
  if (write) writes++;
  try {
    const result = await send<T>(method, path, body, background);
    if (write) mutationListeners.forEach((l) => l(path));
    return result;
  } finally {
    setInflight(-1);
    if (write && --writes === 0) {
      idleWaiters.forEach((w) => w());
      idleWaiters.clear();
    }
  }
}

async function send<T>(method: string, path: string, body?: unknown, background = false, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: payload, cache: "no-store" });
  } catch {
    throw new ApiError(0, "network", "Cannot reach the Nigraan API. It may be waking up - retry in a few seconds.");
  }
  // a background prefetch never signs the user out; the screen's own request decides
  if (res.status === 401 && !background && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    clearSession();
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
  }
  const isJson = res.headers.get("content-type")?.includes("application/json");
  if (!res.ok) {
    const err = isJson ? await res.json() : { code: "error", message: await res.text() };
    throw new ApiError(res.status, err.code ?? "error", err.message ?? "Request failed", err.field);
  }
  return (isJson ? res.json() : res.text()) as Promise<T>;
}

export const api = {
  get: <T,>(p: string, opts: { background?: boolean } = {}) => request<T>("GET", p, undefined, opts.background),
  post: <T,>(p: string, body?: unknown) => request<T>("POST", p, body ?? {}),
  patch: <T,>(p: string, body?: unknown) => request<T>("PATCH", p, body ?? {}),
  upload: <T,>(p: string, form: FormData) => request<T>("POST", p, form),
};
