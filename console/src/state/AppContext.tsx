import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { DATA_SOURCE, API_BASE, PLATFORM_BASE } from '@/data/client';
import { DEFAULT_SCENARIO_ID, getScenario, isScenarioId } from '@/data/scenarios';
import type { DataSourceMode, Scenario, ScenarioId } from '@/types';

const SCENARIO_STORAGE_KEY = 'tracesphere.scenario';

const ENV_LABEL = import.meta.env.VITE_ENV_LABEL ?? 'ZSvirt 智算云 · 演示环境';

interface AppContextValue {
  /** 数据源模式，由 VITE_DATA_SOURCE 在构建期决定，运行时只读。 */
  dataSource: DataSourceMode;
  apiBase: string;
  platformBase: string;
  envLabel: string;
  scenario: Scenario;
  scenarioId: ScenarioId;
  setScenario: (id: ScenarioId) => void;
  /** 全局「刷新」信号：+1 触发各页重新取数。 */
  refreshToken: number;
  refresh: () => void;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

function initialScenario(): ScenarioId {
  const fromEnv = import.meta.env.VITE_DEFAULT_SCENARIO;
  if (isScenarioId(fromEnv)) return fromEnv;
  try {
    const stored = window.localStorage.getItem(SCENARIO_STORAGE_KEY);
    if (isScenarioId(stored)) return stored;
  } catch {
    /* localStorage 不可用时回落到默认值 */
  }
  return DEFAULT_SCENARIO_ID;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [scenarioId, setScenarioId] = useState<ScenarioId>(initialScenario);
  const [refreshToken, setRefreshToken] = useState(0);

  const setScenario = useCallback((id: ScenarioId) => {
    setScenarioId(id);
    try {
      window.localStorage.setItem(SCENARIO_STORAGE_KEY, id);
    } catch {
      /* 忽略持久化失败 */
    }
  }, []);

  const refresh = useCallback(() => setRefreshToken((t) => t + 1), []);

  const value = useMemo<AppContextValue>(
    () => ({
      dataSource: DATA_SOURCE,
      apiBase: API_BASE,
      platformBase: PLATFORM_BASE,
      envLabel: ENV_LABEL,
      scenario: getScenario(scenarioId),
      scenarioId,
      setScenario,
      refreshToken,
      refresh,
    }),
    [scenarioId, setScenario, refreshToken, refresh],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp 必须在 AppProvider 内使用');
  return ctx;
}
