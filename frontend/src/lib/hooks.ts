"use client";
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { api, ApiError, onMutation, writesSettled, writing } from "@/lib/api";

// Shared response cache (stale-while-revalidate). Revisiting a page renders the last response instantly and
// refreshes it in the background; hovering a nav link prefetches its data. Entries are keyed by path, so a
// page never shows data that belongs to another path.
type Entry = { data?: unknown; error?: ApiError; at: number };

const entries = new Map<string, Entry>();
const inflight = new Map<string, { seq: number; promise: Promise<unknown> }>();
const subscribers = new Map<string, Set<() => void>>();
const FRESH_MS = 5000;
let seq = 0;

const emit = (path: string) => subscribers.get(path)?.forEach((cb) => cb());
const watched = (path: string) => (subscribers.get(path)?.size ?? 0) > 0;

/**
 * Fetch `path` into the cache. Concurrent calls share one request unless `force` starts a newer one.
 * A `background` fetch (prefetch) only fills the cache: its errors are dropped, nobody is signed out.
 */
export function load<T>(path: string, force = false, background = false): Promise<T> {
  const running = inflight.get(path);
  if (running && !force) return running.promise as Promise<T>;
  const id = ++seq;
  const latest = () => inflight.get(path)?.seq === id;
  const promise = api.get<T>(path, { background }).then(
    (data) => {
      if (latest()) {
        inflight.delete(path);
        entries.set(path, { data, at: Date.now() });
        emit(path);
      }
      return data;
    },
    (error: ApiError) => {
      if (!latest()) throw error;
      inflight.delete(path);
      // a prefetch failure is forgotten unless a screen is already waiting on this path
      if (!background || watched(path)) {
        // keep showing the last good data through network blips, but not when the record itself is gone
        const keep = error.status === 0 || error.status >= 500;
        entries.set(path, { data: keep ? entries.get(path)?.data : undefined, error, at: Date.now() });
        emit(path);
      }
      throw error;
    },
  );
  inflight.set(path, { seq: id, promise });
  return promise;
}

const isFresh = (path: string) => {
  const e = entries.get(path);
  return inflight.has(path) || (!!e && !e.error && Date.now() - e.at < FRESH_MS);
};

/** Refresh `path` for a screen that is showing it, unless a fresh copy is already there or on its way. */
function revalidate(path: string) {
  if (!isFresh(path)) load(path).catch(() => {});
}

/** Warm the cache in the background (hovered nav link, idle time). Skipped while data is being written. */
export function prefetch(path: string) {
  if (!writing() && !isFresh(path)) load(path, false, true).catch(() => {});
}

/** Mark every response stale and refetch what is on screen. */
export function invalidateAll() {
  for (const [path, e] of entries) {
    if (watched(path)) load(path, true).catch(() => {});
    else e.at = 0;
  }
}

/** After a demo reset the old responses describe a different company state; forget the ones not on screen. */
export function forgetUnwatched() {
  for (const path of [...entries.keys()]) if (!watched(path)) entries.delete(path);
}

/** Warm the cache one path at a time (used when the browser is idle). */
export async function warm(paths: string[]) {
  for (const path of paths) {
    await writesSettled();
    prefetch(path);
    await inflight.get(path)?.promise.catch(() => undefined);
  }
}

// Any write (approve, resolve, upload...) can change what other pages show.
if (typeof window !== "undefined") onMutation(() => invalidateAll());

/** Fetch `path` (re-fetches when it changes) through the shared cache. */
export function useApi<T>(path: string | null) {
  const subscribe = useCallback(
    (cb: () => void) => {
      if (!path) return () => {};
      let set = subscribers.get(path);
      if (!set) subscribers.set(path, (set = new Set()));
      set.add(cb);
      return () => {
        set.delete(cb);
      };
    },
    [path],
  );
  const entry = useSyncExternalStore(subscribe, () => (path ? entries.get(path) : undefined), () => undefined);
  useEffect(() => {
    if (path) revalidate(path);
  }, [path]);
  const reload = useCallback(async () => {
    if (path) await load(path).catch(() => undefined);
  }, [path]);
  const data = entry?.data === undefined ? null : (entry.data as T);
  return { data, error: data === null ? (entry?.error ?? null) : null, loading: !entry, reload };
}
