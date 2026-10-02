import type { CSSProperties } from 'react';

export type IconName =
  | 'topology'
  | 'pulse'
  | 'alert'
  | 'diagnose'
  | 'rule'
  | 'evidence'
  | 'clock'
  | 'search'
  | 'refresh'
  | 'focus'
  | 'plus'
  | 'minus'
  | 'fit'
  | 'chevron'
  | 'external'
  | 'layers'
  | 'task'
  | 'box'
  | 'server'
  | 'cloud'
  | 'arrow-right'
  | 'check'
  | 'warning'
  | 'info';

/**
 * 控制台自绘图标集：统一 16×16 网格、1.5px 描边、无填充。
 * 目的：与拓扑/曲线里的几何语言一致，避免通用图标库的模板感。
 */
const PATHS: Record<IconName, string> = {
  topology: 'M2 4.5h4v3H2zM10 2h4v3h-4zM10 11h4v3h-4zM6 6v6.5M6 12.5h4M6 6h4',
  pulse: 'M1.5 8h3l1.8-4.6L9 12.6 10.8 8h3.7',
  alert: 'M8 2.2 14.4 13H1.6L8 2.2ZM8 6.4v3.4M8 11.4v.6',
  diagnose: 'M2.2 13.4 6 9.6M6 9.6a4.2 4.2 0 1 0-1.2-1.2L2.2 11.2v2.2h2.2ZM11 5.2h3.2M11 8h3.2M11 10.8h2',
  rule: 'M3.5 1.8h6.2L12.5 4.6v9.6H3.5zM9.7 1.8v2.8h2.8M5.4 8.6h5.2M5.4 11h5.2',
  evidence: 'M2 3.2h12M2 8h12M2 12.8h7.5M12.6 10.6v4.2M10.5 12.7h4.2',
  clock: 'M8 1.9a6.1 6.1 0 1 0 0 12.2A6.1 6.1 0 0 0 8 1.9ZM8 4.6V8l2.6 1.6',
  search: 'M7 1.9a5.1 5.1 0 1 0 0 10.2A5.1 5.1 0 0 0 7 1.9ZM10.8 10.8l3.4 3.4',
  refresh: 'M13.4 8a5.4 5.4 0 1 1-1.6-3.8M13.6 2v3.2h-3.2',
  focus: 'M8 3.2v9.6M3.2 8h9.6M8 1.6a6.4 6.4 0 1 0 0 12.8A6.4 6.4 0 0 0 8 1.6Z',
  plus: 'M8 3v10M3 8h10',
  minus: 'M3 8h10',
  fit: 'M2 5.6V2h3.6M14 5.6V2h-3.6M2 10.4V14h3.6M14 10.4V14h-3.6',
  chevron: 'M5.6 3.6 10 8l-4.4 4.4',
  external: 'M9.4 2.2h4.4v4.4M13.8 2.2 8 8M11.4 9.6v4.2H2.2V4.6h4.2',
  layers: 'M8 1.8 14 5l-6 3.2L2 5l6-3.2ZM2 8.4l6 3.2 6-3.2M2 11.4l6 3.2 6-3.2',
  task: 'M2.4 4.2h2.6v2.6H2.4zM2.4 10h2.6v2.6H2.4zM6.6 5.5h7M6.6 11.3h7',
  box: 'M8 1.9 14 5.4v5.2L8 14.1 2 10.6V5.4L8 1.9ZM2 5.4 8 8.9l6-3.5M8 8.9v5.2',
  server: 'M2 2.6h12v4.2H2zM2 9.2h12v4.2H2zM4.6 4.7h.01M4.6 11.3h.01',
  cloud: 'M4.4 12.4h7.8a3 3 0 0 0 .3-6 4.4 4.4 0 0 0-8.5.9 2.7 2.7 0 0 0 .4 5.1Z',
  'arrow-right': 'M2.6 8h10.8M9.4 4.2 13.2 8l-3.8 3.8',
  check: 'M3.2 8.4 6.4 11.6 12.8 4.6',
  warning: 'M8 2.6 14.2 13H1.8L8 2.6ZM8 6.6v3.2M8 11.6v.5',
  info: 'M8 1.9a6.1 6.1 0 1 0 0 12.2A6.1 6.1 0 0 0 8 1.9ZM8 7.2v4M8 4.8v.5',
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  style?: CSSProperties;
  strokeWidth?: number;
  title?: string;
}

export function Icon({ name, size = 16, className, style, strokeWidth = 1.5, title }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      className={className}
      style={{ flex: 'none', ...style }}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
    >
      {title ? <title>{title}</title> : null}
      <path d={PATHS[name]} />
    </svg>
  );
}

export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      {/* 十字准星 + 落点：TraceSphere 的“定位故障点”语义 */}
      <path d="M2 12h6.2M15.8 12H22M12 2v6.2M12 15.8V22" stroke="#0F1318" strokeWidth="1.4" />
      <circle cx="12" cy="12" r="3.4" stroke="#2B5B8F" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="6.6" stroke="#C3CAD3" strokeWidth="1.1" strokeDasharray="2 2.4" />
      <circle cx="12" cy="12" r="1.15" fill="#C0392B" />
    </svg>
  );
}
