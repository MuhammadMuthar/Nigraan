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

async function request<T>(method: string, path: string, body?: unknown, init: RequestInit = {}): Promise<T> {
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
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
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
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, body?: unknown) => request<T>("POST", p, body ?? {}),
  patch: <T,>(p: string, body?: unknown) => request<T>("PATCH", p, body ?? {}),
  upload: <T,>(p: string, form: FormData) => request<T>("POST", p, form),
};
