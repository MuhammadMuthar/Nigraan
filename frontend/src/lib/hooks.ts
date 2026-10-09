"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type State<T> = { path: string | null; data: T | null; error: ApiError | null };

/** Fetch `path` (re-fetches when it changes). Results are tagged with their path so stale data never shows. */
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<State<T>>({ path: null, data: null, error: null });
  useEffect(() => {
    if (!path) return;
    let alive = true;
    api.get<T>(path).then(
      (data) => alive && setState({ path, data, error: null }),
      (error) => alive && setState({ path, data: null, error: error as ApiError }),
    );
    return () => {
      alive = false;
    };
  }, [path]);
  const reload = useCallback(async () => {
    if (!path) return;
    try {
      setState({ path, data: await api.get<T>(path), error: null });
    } catch (error) {
      setState({ path, data: null, error: error as ApiError });
    }
  }, [path]);
  const current = state.path === path;
  return { data: current ? state.data : null, error: current ? state.error : null, loading: !current, reload };
}
