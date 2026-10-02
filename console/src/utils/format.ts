/**
 * 时间与数值格式化。控制台统一使用 UTC 展示，避免跨时区演示歧义。
 */

const PAD = (n: number) => String(n).padStart(2, '0');

function parse(input: string | number | Date | undefined | null): Date | null {
  if (input === undefined || input === null || input === '') return null;
  const d = input instanceof Date ? input : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 2026-09-20 08:25:37 */
export function fmtDateTime(input: string | number | Date): string {
  const d = parse(input);
  if (!d) return '—';
  return `${d.getUTCFullYear()}-${PAD(d.getUTCMonth() + 1)}-${PAD(d.getUTCDate())} ${PAD(
    d.getUTCHours(),
  )}:${PAD(d.getUTCMinutes())}:${PAD(d.getUTCSeconds())}`;
}

/** 08:25:37.412 */
export function fmtClock(input: string | number | Date): string {
  const d = parse(input);
  if (!d) return '—';
  return `${PAD(d.getUTCHours())}:${PAD(d.getUTCMinutes())}:${PAD(d.getUTCSeconds())}`;
}

/** 08:25:37.412（含毫秒，证据列表用） */
export function fmtClockMs(input: string | number | Date): string {
  const d = parse(input);
  if (!d) return '—';
  return `${fmtClock(d)}.${String(d.getUTCMilliseconds()).padStart(3, '0')}`;
}

export function toEpochSeconds(input: string | number | Date): number {
  const d = parse(input);
  return d ? Math.floor(d.getTime() / 1000) : 0;
}

/** 相对时间：+2.0s / -1.4m */
export function fmtDelta(fromSec: number, toSec: number): string {
  const delta = toSec - fromSec;
  const abs = Math.abs(delta);
  const sign = delta >= 0 ? '+' : '−';
  if (abs < 1) return `${sign}${(abs * 1000).toFixed(0)}ms`;
  if (abs < 60) return `${sign}${abs.toFixed(abs < 10 ? 1 : 0)}s`;
  if (abs < 3600) return `${sign}${(abs / 60).toFixed(1)}m`;
  return `${sign}${(abs / 3600).toFixed(1)}h`;
}

/** 窗口描述：最近 15 分钟 */
export function fmtWindowLabel(seconds: number): string {
  if (seconds % 3600 === 0) return `最近 ${seconds / 3600} 小时`;
  if (seconds % 60 === 0) return `最近 ${seconds / 60} 分钟`;
  return `最近 ${seconds} 秒`;
}

/** 紧凑数值：1.46e7 → 14.6M */
export function fmtValue(value: number | undefined | null, unit?: string): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  if (unit === 'byte') {
    const abs = Math.abs(value);
    if (abs >= 1024 * 1024 * 1024) return `${(value / 1024 / 1024 / 1024).toFixed(2)} GiB`;
    if (abs >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MiB`;
    if (abs >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
    return `${value} B`;
  }
  if (unit === 'usec') {
    const abs = Math.abs(value);
    if (abs >= 1e6) return `${(value / 1e6).toFixed(2)} s`;
    if (abs >= 1e3) return `${(value / 1e3).toFixed(1)} ms`;
    return `${value} µs`;
  }
  if (unit === 'ratio') return value.toFixed(2);
  if (unit === 'percent') return `${value.toFixed(2)}%`;
  if (unit === 'ms') {
    if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)} s`;
    return `${value.toFixed(0)} ms`;
  }
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}

export function fmtUnitSuffix(unit?: string): string {
  switch (unit) {
    case 'count':
      return '次';
    case 'ratio':
      return '';
    case 'percent':
      return '';
    case 'ms':
      return '';
    case 'usec':
      return '';
    case 'byte':
      return '';
    default:
      return '';
  }
}

/** 证据 ID 短展示：ev-0001 */
export function shortId(id: string, head = 14): string {
  if (id.length <= head) return id;
  return `${id.slice(0, head)}…`;
}

/** 容器/资源 ID 折叠：container:7196bcad3bc1 */
export function fmtResourceId(id: string): string {
  return id;
}

export function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max);
}

/** 由「生成时刻 + 窗口秒数」推导窗口区间（fixture 模式离线计算） */
export function windowFromGeneratedAt(generatedAt: string, seconds: number) {
  const to = parse(generatedAt) ?? new Date();
  const from = new Date(to.getTime() - seconds * 1000);
  return from.toISOString().replace(/\.\d{3}Z$/, 'Z');
}
