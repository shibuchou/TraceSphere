import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { useApp } from '@/state/AppContext';
import type { MetaResponse } from '@/types';

/**
 * 规则库取数（GET /api/v1/rules；夹具模式回落 meta.json 的 rules 段）。
 *
 * 抽成独立 hook：诊断页与「规则库」面板共享同一份缓存语义，
 * 避免两处各写一遍加载 / 错误 / 重试逻辑。
 */
export function useRuleLibrary() {
  const app = useApp();
  return useAsync<MetaResponse>(
    (signal) => api.getMeta({ signal }),
    [app.refreshToken],
  );
}
