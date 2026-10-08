import type { ReactNode } from 'react';
import styles from './Tags.module.css';
import {
  COLORS,
  EVIDENCE_KIND_TEXT,
  INCIDENT_STATUS_TEXT,
  LAYER_COLOR,
  LAYER_TEXT,
  SEVERITY_COLOR,
  SEVERITY_TEXT,
  STATUS_COLOR,
  STATUS_TEXT,
} from '@/theme/tokens';
import type { EvidenceKind, EvidenceLayer, IncidentStatus, NodeStatus, Severity } from '@/types';

interface BaseTagProps {
  className?: string;
  tiny?: boolean;
  title?: string;
}

function cx(...parts: (string | false | undefined)[]) {
  return parts.filter(Boolean).join(' ');
}

/* ---------------------------- 健康状态 ---------------------------- */

export function StatusTag({
  status,
  tiny,
  title,
  shape = 'ring',
  showText = true,
}: BaseTagProps & { status: NodeStatus; shape?: 'ring' | 'dot'; showText?: boolean }) {
  const color = STATUS_COLOR[status] ?? COLORS.unknown;
  return (
    <span
      className={cx(styles.tag, tiny && styles.tiny, styles.mono)}
      style={{ color }}
      title={title ?? `状态：${STATUS_TEXT[status] ?? status}`}
    >
      <i className={shape === 'dot' ? styles.dot : styles.ring} />
      {showText ? STATUS_TEXT[status] ?? status : null}
    </span>
  );
}

/* ---------------------------- 证据严重度 ---------------------------- */

export function SeverityTag({
  severity,
  tiny,
  title,
  showText = true,
}: BaseTagProps & { severity: Severity; showText?: boolean }) {
  const color = SEVERITY_COLOR[severity] ?? COLORS.inkTertiary;
  return (
    <span
      className={cx(styles.tag, tiny && styles.tiny, styles.mono)}
      style={{ color }}
      title={title ?? `严重度：${SEVERITY_TEXT[severity] ?? severity}`}
    >
      <i className={styles.pulse} />
      {showText ? SEVERITY_TEXT[severity] ?? severity : null}
    </span>
  );
}

/* ---------------------------- 层级 ---------------------------- */

export function LayerTag({ layer, tiny }: BaseTagProps & { layer: EvidenceLayer }) {
  const color = LAYER_COLOR[layer] ?? COLORS.inkTertiary;
  return (
    <span className={cx(styles.tag, styles.layer, tiny && styles.tiny, styles.mono)} style={{ color }}>
      {LAYER_TEXT[layer] ?? (layer ? layer : '未知层级')}
    </span>
  );
}

/* ---------------------------- 证据来源类别 ---------------------------- */

export function EvidenceKindTag({ kind, tiny }: BaseTagProps & { kind: EvidenceKind }) {
  return (
    <span className={cx(styles.tag, tiny && styles.tiny, styles.mono)} style={{ color: COLORS.inkSecondary }}>
      <span className={styles.label}>来源</span>
      {EVIDENCE_KIND_TEXT[kind] ?? kind}
    </span>
  );
}

/* ---------------------------- 告警状态 ---------------------------- */

export function IncidentStatusTag({ status, tiny }: BaseTagProps & { status: IncidentStatus }) {
  const color =
    status === 'open'
      ? COLORS.critical
      : status === 'acknowledged'
        ? COLORS.warning
        : status === 'resolved'
          ? COLORS.healthy
          : COLORS.unknown;
  return (
    <span className={cx(styles.tag, tiny && styles.tiny, styles.mono)} style={{ color }}>
      {INCIDENT_STATUS_TEXT[status] ?? status}
    </span>
  );
}

/* ---------------------------- 中性标签 ---------------------------- */

export function PlainTag({
  children,
  color = COLORS.inkSecondary,
  tiny,
  title,
  mono = true,
  dashed = false,
}: {
  children: ReactNode;
  color?: string;
  tiny?: boolean;
  title?: string;
  mono?: boolean;
  dashed?: boolean;
}) {
  return (
    <span
      className={cx(styles.tag, tiny && styles.tiny, mono && styles.mono, dashed && styles.layer)}
      style={{ color, borderStyle: dashed ? 'dashed' : undefined }}
      title={title}
    >
      {children}
    </span>
  );
}

const monoFont = { fontFamily: 'var(--ts-mono)' };
export { monoFont };
