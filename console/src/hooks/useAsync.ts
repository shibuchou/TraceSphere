import { useCallback, useEffect, useRef, useState } from 'react';
import { toApiError } from '@/data/errors';
import type { ApiError } from '@/data/errors';

export interface AsyncState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  /** 已成功加载过一次（用于「刷新中」与「首次加载」区分） */
  loaded: boolean;
  reload: () => void;
  setData: (next: T) => void;
}

/**
 * 统一的数据请求 hook。
 *
 * - deps 变化即重新拉取，并用 AbortController 取消上一次（避免竞态覆盖）；
 * - `refreshKey` 用于顶栏「刷新」按钮强制重取；
 * - `pollMs > 0` 时按间隔静默轮询（失败不打断已有数据）。
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  options: { pollMs?: number; enabled?: boolean } = {},
): AsyncState<T> {
  const { pollMs = 0, enabled = true } = options;
  const [data, setDataState] = useState<T | undefined>(undefined);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [loading, setLoading] = useState(enabled);
  const [loaded, setLoaded] = useState(false);
  const [tick, setTick] = useState(0);

  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((next: T) => {
    setDataState(next);
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let alive = true;
    setLoading(true);

    loaderRef
      .current(controller.signal)
      .then((result) => {
        if (!alive) return;
        setDataState(result);
        setError(undefined);
        setLoaded(true);
      })
      .catch((cause: unknown) => {
        if (!alive) return;
        const err = toApiError(cause);
        if (err.message === '请求已取消') return;
        setError(err);
      })
      .finally(() => {
        if (!alive) return;
        setLoading(false);
      });

    return () => {
      alive = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);

  useEffect(() => {
    if (!pollMs || !enabled) return;
    const timer = window.setInterval(() => setTick((t) => t + 1), pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, enabled]);

  return { data, error, loading, loaded, reload, setData };
}
