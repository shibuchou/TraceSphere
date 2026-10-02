import { Popover } from 'antd';
import styles from './DataSourceBadge.module.css';
import { Icon } from './Icon';
import { useApp } from '@/state/AppContext';
import type { DataSourceMode, SourceMode } from '@/types';
import { SOURCE_TEXT } from '@/theme/tokens';

type BadgeMode = DataSourceMode | SourceMode;

const MODE_TEXT: Record<string, string> = {
  api: 'LIVE',
  fixture: 'REPLAY',
  real: '真实',
  degraded: '降级',
  mock: '回放',
  unavailable: '不可用',
  off: '未启用',
};

const MODE_CLASS: Record<string, keyof typeof styles> = {
  api: 'source_real',
  fixture: 'source_mock',
  real: 'source_real',
  degraded: 'source_degraded',
  mock: 'source_mock',
  unavailable: 'source_unavailable',
  off: 'source_unavailable',
};

const styleFor = (mode: string): string => {
  const key = MODE_CLASS[mode];
  return key ? (styles[key] as string) : (styles.source_unavailable as string);
};

export function DataSourceBadge({
  mode,
  blink = false,
  compact = false,
}: {
  /** 不传则取全局构建期模式（api / fixture） */
  mode?: BadgeMode;
  blink?: boolean;
  compact?: boolean;
}) {
  const app = useApp();
  const value = mode ?? app.dataSource;
  const cls = styleFor(value);

  const content = (
    <div className={styles.popover}>
      <div className="ts-eyebrow">当前数据源</div>
      <div style={{ fontWeight: 600, marginTop: 2 }}>
        {value === 'api' ? '真实诊断服务（api 模式）' : value === 'fixture' ? '本地夹具回放（fixture 模式）' : MODE_TEXT[value]}
      </div>
      <dl className={styles.kv}>
        <dt>请求基址</dt>
        <dd>{app.dataSource === 'api' ? app.apiBase : 'src/mocks/*.json'}</dd>
        <dt>切换方式</dt>
        <dd>构建期环境变量 VITE_DATA_SOURCE</dd>
        <dt>平台地址</dt>
        <dd>{app.platformBase}</dd>
      </dl>
      <div style={{ marginTop: 8, color: 'var(--ts-ink-2)' }}>切换模式（需重启 dev server）：</div>
      <code>{'# fixture 回放，无需后端\nVITE_DATA_SOURCE=fixture npm run dev\n\n# api 联调（默认）\nVITE_DATA_SOURCE=api VITE_RCA_BASE_URL=http://127.0.0.1:8010 npm run dev'}</code>
      <div style={{ color: 'var(--ts-ink-3)', fontSize: 11 }}>
        Windows PowerShell 用 <code style={{ display: 'inline', padding: '0 3px' }}>$env:VITE_DATA_SOURCE="fixture"</code> 后执行 npm run dev。
      </div>
    </div>
  );

  return (
    <Popover content={content} placement="bottomRight" trigger="hover" mouseEnterDelay={0.15}>
      <span className={`${styles.source} ${cls}`} title="数据源状态（悬停查看切换方式）">
        <i className={`${styles.led} ${blink ? styles.ledBlink : ''}`} />
        {compact ? null : <span>{app.dataSource === 'api' ? 'API' : 'FIXTURE'}</span>}
        <span style={{ opacity: 0.75 }}>{MODE_TEXT[value] ?? SOURCE_TEXT[value] ?? value}</span>
      </span>
    </Popover>
  );
}

/** 页脚用的多来源状态条：real / degraded / mock 一眼可辨（API.md §6）。 */
export function SourceStatusStrip({ source }: { source?: Record<string, SourceMode | undefined> }) {
  const entries = Object.entries(source ?? {}).filter(([, v]) => Boolean(v));
  if (entries.length === 0) return null;
  return (
    <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      {entries.map(([name, value]) => (
        <span
          key={name}
          className={`${styles.source} ${styleFor(String(value))}`}
          style={{ height: 18, fontSize: 10 }}
        >
          <i className={styles.led} />
          {name}: {SOURCE_TEXT[value as string] ?? value}
        </span>
      ))}
    </span>
  );
}

export function IconInfo({ label }: { label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--ts-ink-3)', fontSize: 11 }}>
      <Icon name="info" size={12} />
      {label}
    </span>
  );
}
