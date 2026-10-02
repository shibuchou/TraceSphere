import type { CSSProperties, ReactNode } from 'react';
import { Tooltip } from 'antd';
import styles from './PageHead.module.css';
import { COLORS } from '@/theme/tokens';

export function PageHead({
  title,
  sub,
  desc,
  right,
  footer,
}: {
  title: string;
  sub?: string;
  desc?: ReactNode;
  right?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className={styles.pageHead}>
      <div className={styles.pageTitleWrap}>
        <h1 className={styles.pageTitle}>
          {title}
          {sub ? <span className={styles.pageTitleSub}>{sub}</span> : null}
        </h1>
        {desc ? <div className={styles.pageDesc}>{desc}</div> : null}
        {footer}
      </div>
      {right ? <div className={styles.toolbar}>{right}</div> : null}
    </div>
  );
}

export function MetricCard({
  label,
  value,
  foot,
  accent = COLORS.inkTertiary,
  hint,
  active = false,
  onClick,
}: {
  label: string;
  value: number | string;
  foot?: string;
  accent?: string;
  hint?: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const card = (
    <div
      className={styles.metric}
      style={{
        '--metric-accent': accent,
        '--metric-active-border': active ? accent : undefined,
        cursor: onClick ? 'pointer' : undefined,
      } as CSSProperties}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue} style={{ color: accent }}>
        {value}
      </span>
      {foot ? <span className={styles.metricFoot}>{foot}</span> : null}
    </div>
  );
  if (!hint) return card;
  return (
    <Tooltip title={hint} placement="topLeft">
      {card}
    </Tooltip>
  );
}
