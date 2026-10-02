import type { ReactNode } from 'react';
import { Button } from 'antd';
import styles from './States.module.css';
import { Icon } from './Icon';
import type { ApiErrorShape } from '@/types';

/* ---------------------------- 加载态 ---------------------------- */

export function LoadingPanel({ rows = 4, label = '正在取数' }: { rows?: number; label?: string }) {
  return (
    <div className={styles.skeleton} role="status" aria-live="polite" aria-label={label}>
      <div className="ts-eyebrow">{label}…</div>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={styles.bar}
          style={{ width: `${92 - i * 11}%`, animationDelay: `${i * 90}ms` }}
        />
      ))}
    </div>
  );
}

export function InlineLoading({ label }: { label: string }) {
  return (
    <div className={styles.inline} style={{ borderLeftColor: 'var(--ts-primary)' }}>
      <Icon name="refresh" size={14} />
      <span>{label}</span>
    </div>
  );
}

/* ---------------------------- 空状态 ---------------------------- */

export function EmptyState({
  title,
  description,
  action,
  icon = 'info',
}: {
  title: string;
  description: ReactNode;
  action?: ReactNode;
  icon?: 'info' | 'warning';
}) {
  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <span className={styles.iconMuted}>
          <Icon name={icon} size={16} />
        </span>
        {title}
      </div>
      <div className={styles.body}>{description}</div>
      {action ? <div className={styles.actions}>{action}</div> : null}
    </div>
  );
}

/* ---------------------------- 错误态 ---------------------------- */

export interface ErrorStateProps {
  error: ApiErrorShape;
  onRetry?: () => void;
  extra?: ReactNode;
}

/**
 * 后端未启动时的兜底：给出「发生了什么 / 请求路径 / 怎么办」。
 * 保证 api 模式下服务不可用时页面不白屏。
 */
export function ErrorState({ error, onRetry, extra }: ErrorStateProps) {
  const isFixtureError = error.mode === 'fixture';
  return (
    <div className={`${styles.wrap} ${styles.wrapError}`} role="alert">
      <div className={styles.head}>
        <span className={styles.iconCritical}>
          <Icon name="warning" size={16} />
        </span>
        {isFixtureError ? '夹具数据缺失' : '无法读取诊断服务'}
      </div>
      <div className={styles.body}>{error.message}</div>
      <code className={styles.code}>
        {error.mode.toUpperCase()} · {error.path}
        {error.status ? ` · HTTP ${error.status}` : ''}
      </code>
      <div className={styles.hint}>{error.hint}</div>
      <div className={styles.actions}>
        {onRetry ? (
          <Button size="small" onClick={onRetry} icon={<Icon name="refresh" size={13} />}>
            重试
          </Button>
        ) : null}
        {extra}
      </div>
    </div>
  );
}
