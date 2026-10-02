import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts';
import styles from './MetricCharts.module.css';
import { COLORS, MONO_FONT, SANS_FONT } from '@/theme/tokens';
import { fmtValue } from '@/utils/format';
import type { MetricSeries, MetricsSeriesResponse } from '@/types';

/** 单实例 ECharts 容器：负责 init / resize / dispose 生命周期。 */
function useChart(option: echarts.EChartsCoreOption, height: number) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    chartRef.current?.resize();
  }, [height]);

  return ref;
}

interface SeriesChartProps {
  series: MetricSeries;
  height?: number;
  /** 展示开关：标题栏右侧 */
  headerRight?: React.ReactNode;
}

/** 单条曲线的独立图：不同单位不共轴，避免误导性缩放。 */
export function SeriesChart({ series, height = 168, headerRight }: SeriesChartProps) {
  const option = useMemo<echarts.EChartsCoreOption>(() => {
    const thresholdMarks = series.thresholds.map((t) => ({
      yAxis: t.value,
      lineStyle: { color: t.color ?? COLORS.critical, type: 'dashed' as const, width: 1 },
      label: {
        formatter: `${t.label} ${fmtValue(t.value, series.unit)}`,
        position: 'insideEndTop' as const,
        color: t.color ?? COLORS.critical,
        fontFamily: MONO_FONT,
        fontSize: 10,
        backgroundColor: 'rgba(255,255,255,0.85)',
        padding: [1, 3] as [number, number],
      },
    }));

    const values = series.points.map(([, v]) => v);
    const maxV = values.length ? Math.max(...values) : 1;
    const hasThresholdAbove = series.thresholds.some((t) => t.value > maxV);
    const yMax = hasThresholdAbove
      ? Math.max(...series.thresholds.map((t) => t.value)) * 1.08
      : maxV === 0
        ? 1
        : maxV * 1.25;

    return {
      animation: false,
      grid: { left: 54, right: 14, top: 14, bottom: 22 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: COLORS.ruleStrong } },
        backgroundColor: '#ffffff',
        borderColor: COLORS.rule,
        borderWidth: 1,
        textStyle: { color: COLORS.ink, fontSize: 11, fontFamily: MONO_FONT },
        formatter: (params: unknown) => {
          const list = Array.isArray(params) ? params : [params];
          const first = list[0] as { value?: [number, number] } | undefined;
          if (!first?.value) return '';
          const t = new Date(first.value[0] * 1000);
          const time = `${String(t.getUTCHours()).padStart(2, '0')}:${String(t.getUTCMinutes()).padStart(2, '0')}:${String(t.getUTCSeconds()).padStart(2, '0')}`;
          const v = first.value[1];
          return `<b>${series.label}</b><br/>${time} UTC · ${fmtValue(v, series.unit)}`;
        },
      },
      xAxis: {
        type: 'time',
        axisLine: { lineStyle: { color: COLORS.rule } },
        axisTick: { show: false },
        axisLabel: {
          color: COLORS.inkTertiary,
          fontSize: 10,
          fontFamily: MONO_FONT,
          formatter: (value: number) => {
            const d = new Date(value);
            return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
          },
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: yMax,
        splitNumber: 3,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: COLORS.inkTertiary,
          fontSize: 10,
          fontFamily: MONO_FONT,
          formatter: (value: number) => fmtValue(value, series.unit),
        },
        splitLine: { lineStyle: { color: '#F0F2F5' } },
      },
      series: [
        {
          name: series.label,
          type: 'line',
          showSymbol: false,
          symbolSize: 5,
          smooth: false,
          step: series.unit === 'count' && /throttled|restart|oom_kill/.test(series.name) ? 'end' : false,
          lineStyle: { color: COLORS.primary, width: 1.6 },
          itemStyle: { color: COLORS.primary },
          areaStyle: { color: 'rgba(43, 91, 143, 0.08)' },
          data: series.points.map(([t, v]) => [t * 1000, v]),
          markLine: thresholdMarks.length
            ? { symbol: 'none', silent: true, data: thresholdMarks }
            : undefined,
        },
      ],
    };
  }, [series]);

  const ref = useChart(option, height);

  if (series.points.length === 0) {
    return (
      <div className={styles.chart}>
        <div className={styles.chartHead}>
          <span className={styles.chartTitle}>{series.label}</span>
        </div>
        <div className={styles.empty}>窗口内无采样点</div>
      </div>
    );
  }

  return (
    <div className={styles.chart}>
      <div className={styles.chartHead}>
        <span className={styles.chartTitle}>
          {series.label} <span className={styles.chartMeta}>{series.name}</span>
        </span>
        <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {headerRight}
          <span className={styles.chartMeta}>{series.points.length} 点</span>
        </span>
      </div>
      <div className={styles.canvas} ref={ref} style={{ height }} />
    </div>
  );
}

/** 指标曲线组：三态（加载 / 错误 / 正常）由外层的 AsyncBoundary 负责，这里只管渲染。 */
export function MetricSeriesPanel({
  data,
  height = 168,
  columns,
}: {
  data: MetricsSeriesResponse;
  height?: number;
  columns?: number;
}) {
  if (data.series.length === 0) {
    return <div className={styles.empty}>该资源在窗口内没有可绘制的指标序列。</div>;
  }
  return (
    <div
      className={styles.grid}
      style={{ gridTemplateColumns: `repeat(${columns ?? (data.series.length > 2 ? 2 : 1)}, minmax(0, 1fr))` }}
    >
      {data.series.map((s) => (
        <SeriesChart key={s.name} series={s} height={height} />
      ))}
    </div>
  );
}

export const CHART_PALETTE = COLORS;
export const CHART_FONT = { mono: MONO_FONT, sans: SANS_FONT };
