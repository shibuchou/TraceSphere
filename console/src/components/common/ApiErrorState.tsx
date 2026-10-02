import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Button } from 'antd';
import { ErrorState } from './States';
import { Icon } from './Icon';
import { useApp } from '@/state/AppContext';
import { getScenario } from '@/data/scenarios';
import type { ApiErrorShape } from '@/types';

/** 当前场景对应的夹具回放命令（页脚 / 错误态共用同一段文案）。 */
export const FIXTURE_COMMAND = '# Linux / macOS\nVITE_DATA_SOURCE=fixture npm run dev\n\n# Windows PowerShell\n$env:VITE_DATA_SOURCE="fixture"; npm run dev';

/**
 * 错误态 + 数据源指引。
 *
 * 数据源是构建期变量，无法在运行时热切；因此这里给出「当前场景的可复现命令」
 * 而不是一个假的切换按钮——按钮必须真的有效。
 */
export function ApiErrorState({
  error,
  onRetry,
  extra,
}: {
  error: ApiErrorShape;
  onRetry?: () => void;
  extra?: ReactNode;
}) {
  const app = useApp();
  const scenario = getScenario(app.scenarioId);
  return (
    <ErrorState
      error={error}
      onRetry={onRetry}
      extra={
        <>
          <Link to={`/diagnosis?correlation_id=${scenario.correlation_id}`}>
            <Button size="small" icon={<Icon name="diagnose" size={13} />}>
              用夹具场景 {scenario.label} 继续
            </Button>
          </Link>
          {extra}
        </>
      }
    />
  );
}
