"use client";
import { createContext, useCallback, useContext, useSyncExternalStore } from "react";
import { api, clearSession, storeSession, type User } from "@/lib/api";

type Ctx = { user: User | null; ready: boolean; login: (email: string, password: string) => Promise<User>; logout: () => void };
const AuthContext = createContext<Ctx | null>(null);

// localStorage-backed session store, read with useSyncExternalStore (no setState-in-effect, SSR-safe)
const listeners = new Set<() => void>();
let cachedRaw: string | null = null;
let cachedUser: User | null = null;
function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}
function snapshot(): User | null {
  const raw = window.localStorage.getItem("nigraan.user");
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedUser = raw ? (JSON.parse(raw) as User) : null;
  }
  return cachedUser;
}
const notify = () => listeners.forEach((l) => l());
const noopSubscribe = () => () => {};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const user = useSyncExternalStore(subscribe, snapshot, () => null);
  const ready = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post<{ access_token: string; user: User }>("/auth/login", { email, password });
    storeSession(r.access_token, r.user);
    notify();
    return r.user;
  }, []);
  const logout = useCallback(() => {
    clearSession();
    notify();
    window.location.href = "/login";
  }, []);
  return <AuthContext.Provider value={{ user, ready, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const c = useContext(AuthContext);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}

export const ROLE_LABEL: Record<string, string> = { accountant: "Accountant", approver: "Approver", owner: "Owner" };
