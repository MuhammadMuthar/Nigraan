"use client";
import { useEffect, useSyncExternalStore } from "react";
import { PREFS_KEY as KEY } from "@/lib/theme-script";

// Per-browser display preferences (theme, motion, floating button). Read with useSyncExternalStore like the session.
export type ThemePref = "light" | "dark" | "system";
export type Prefs = { theme: ThemePref; animations: boolean; fabHidden: boolean; fabPos: { fx: number; fy: number } | null };

const DEFAULTS: Prefs = { theme: "system", animations: true, fabHidden: false, fabPos: null };
export const OPEN_PREFERENCES_EVENT = "nigraan:open-preferences";

const listeners = new Set<() => void>();
let current: Prefs | null = null;

function load(): Prefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export function getPrefs(): Prefs {
  if (!current) current = load();
  return current;
}

export function setPrefs(patch: Partial<Prefs>) {
  current = { ...getPrefs(), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // private mode: keep the preference for this tab only
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key !== KEY) return;
    current = load();
    cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

export function usePrefs(): Prefs {
  return useSyncExternalStore(subscribe, getPrefs, () => DEFAULTS);
}

const darkQuery = () => window.matchMedia("(prefers-color-scheme: dark)");
function subscribeSystem(cb: () => void) {
  const mq = darkQuery();
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

export function useResolvedTheme(): "light" | "dark" {
  const { theme } = usePrefs();
  const systemDark = useSyncExternalStore(subscribeSystem, () => darkQuery().matches, () => false);
  return theme === "system" ? (systemDark ? "dark" : "light") : theme;
}

function resolve(theme: ThemePref): "light" | "dark" {
  return theme === "system" ? (darkQuery().matches ? "dark" : "light") : theme;
}

function applyTheme(resolved: "light" | "dark") {
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export function motionAllowed() {
  return getPrefs().animations && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Switch theme; where supported, the new theme is revealed in a circle growing from `origin`. */
export function changeTheme(theme: ThemePref, origin?: { x: number; y: number }) {
  const root = document.documentElement;
  const before = root.classList.contains("dark") ? "dark" : "light";
  const after = resolve(theme);
  const commit = () => {
    setPrefs({ theme });
    applyTheme(after);
  };
  if (before === after || typeof document.startViewTransition !== "function" || !motionAllowed()) {
    commit();
    return;
  }
  root.classList.add("theme-vt");
  const transition = document.startViewTransition(commit);
  const x = origin?.x ?? window.innerWidth / 2;
  const y = origin?.y ?? 0;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  transition.ready
    .then(() => {
      root.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 650, easing: "cubic-bezier(0.4, 0, 0.2, 1)", pseudoElement: "::view-transition-new(root)" },
      );
    })
    .catch(() => {});
  transition.finished.finally(() => root.classList.remove("theme-vt"));
}

export function openPreferences() {
  window.dispatchEvent(new Event(OPEN_PREFERENCES_EVENT));
}

/** Keeps <html> classes in sync with the stored preferences and the OS theme. */
export function PreferencesSync() {
  const resolved = useResolvedTheme();
  const { animations } = usePrefs();
  useEffect(() => applyTheme(resolved), [resolved]);
  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", !animations);
  }, [animations]);
  return null;
}

