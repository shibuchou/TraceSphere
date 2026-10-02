import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button, Segmented, Select, Space } from 'antd';
import styles from './pages.module.css';
import { Panel, VStack } from '@/components/common/Panel';
import { Icon } from '@/components/common/Icon';
import { MetricCard, PageHead } from '@/components/common/PageHead';
import { InlineLoading, LoadingPanel } from '@/components/common/States';
import { ApiErrorState } from '@/components/common/ApiErrorState';
import { LayerTag, PlainTag, SeverityTag, StatusTag } from '@/components/common/Tags';
import { SourceStatusStrip } from '@/components/common/DataSourceBadge';
import { LayerTimeline } from '@/components/timeline/LayerTimeline';
import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { useApp } from '@/state/AppContext';
import { COLORS, KIND_TEXT, STATUS_COLOR } from '@/theme/tokens';
import { fmtClock, fmtValue } from '@/utils/format';
import type { NodeStatus, WorkloadHealth, WorkloadMetric } from '@/types';

interface WindowOption {
  label: string;
  seconds: number;
}

/** 时间窗：15m / 1h / 6h（API.md §4.2 的 window_seconds 语义）。 */
const WINDOWS: WindowOption[] = [
  { label: '15 分钟', seconds: 900 },
  { label: '1 小时', seconds: 3600 },
  { label: '6 小时', seconds: 21600 },
];

type SortKey = 'severity' | 'score' | 'failures' | 'name';

const SORT_OPTIONS: { label: string; value: SortKey }[] = [
  { label: '按状态严重度', value: 'severity' },
  { label: '按健康分升序', value: 'score' },
  { label: '按任务失败数', value: 'failures' },
  { label: '按名称', value: 'name' },
];

const SEVERITY_WEIGHT: Record<NodeStatus, number> = { critical: 0, warning: 1, unknown: 2, healthy: 3 };

export function HealthPage() {
  const app = useApp();
  const [searchParams] = useSearchParams();
  const [windowSeconds, setWindowSeconds] = useState<number>(900);
  const [sortKey, setSortKey] = useState<SortKey>('severity');
  const [kindFilter, setKindFilter] = useState<'all' | 'container' | 'service'>('all');

  const overview = useAsync(
    (signal) => api.getOverview(windowSeconds, { signal }),
    [windowSeconds, app.refreshToken],
  );
  const incidents = useAsync((signal) => api.getIncidents({ signal }), [app.refreshToken]);

  const summary = overview.data?.summary;
  const highlightResource = searchParams.get('resource_id') ?? app.scenario.resource_id;

  const workloads = useMemo(() => {
    const list = (overview.data?.workloads ?? []).filter(
      (w) => kindFilter === 'all' || w.kind === kindFilter,
    );
    const sorted = [...list];
    switch (sortKey) {
      case 'severity':
        sorted.sort(
          (a, b) => SEVERITY_WEIGHT[a.status] - SEVERITY_WEIGHT[b.status] || a.health_score - b.health_score,
        );
        break;
      case 'score':
        sorted.sort((a, b) => a.health_score - b.health_score);
        break;
      case 'failures':
        sorted.sort((a, b) => b.task_failures - a.task_failures);
        break;
      case 'name':
        sorted.sort((a, b) => a.name.localeCompare(b.name));
        break;
    }
    return sorted;
  }, [overview.data, sortKey, kindFilter]);

  const windowLabel = WINDOWS.find((w) => w.seconds === windowSeconds)?.label ?? `${windowSeconds}s`;

  if (overview.error && !overview.data) {
    return (
      <div className={styles.page}>
        <PageHead
          title="健康总览"
          sub="GET /api/v1/overview"
          desc="资源健康汇总、工作负载健康卡片与分层事件时间线。"
        />
        <ApiErrorState error={overview.error} onRetry={overview.reload} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHead
        title="健康总览"
        sub={`GET /api/v1/overview?window_seconds=${windowSeconds}`}
        desc="上层看结论（有多少资源不健康、有多少任务失败），中层看哪个工作负载在恶化，下层看事件在什么时刻、哪一层发生。"
        right={
          <Space size={8} wrap>
            <Segmented
              size="small"
              value={windowSeconds}
              onChange={(v) => setWindowSeconds(Number(v))}
              options={WINDOWS.map((w) => ({ label: w.label, value: w.seconds }))}
            />
            <Select
              size="small"
              style={{ width: 148 }}
              value={kindFilter}
              onChange={setKindFilter}
              options={[
                { label: '全部工作负载', value: 'all' },
                { label: '仅容器', value: 'container' },
                { label: '仅服务', value: 'service' },
              ]}
            />
            <Select
              size="small"
              style={{ width: 148 }}
              value={sortKey}
              onChange={setSortKey}
              options={SORT_OPTIONS}
            />
            <Button
              size="small"
              icon={<Icon name="refresh" size={13} />}
              onClick={() => app.refresh()}
              loading={overview.loading && !overview.data}
            >
              刷新
            </Button>
          </Space>
        }
        footer={
          overview.data ? (
            <div
              style={{
                display: 'flex',
                gap: 14,
                alignItems: 'center',
                flexWrap: 'wrap',
                marginTop: 6,
              }}
            >
              <span className="ts-inline-meta">
                窗口 {fmtClock(overview.data.window.from)} → {fmtClock(overview.data.window.to)} UTC ·{' '}
                {windowLabel}
              </span>
              <SourceStatusStrip source={overview.data.source} />
            </div>
          ) : null
        }
      />

      {overview.loading && !overview.data ? (
        <LoadingPanel rows={5} label="加载健康总览" />
      ) : summary ? (
        <>
          <div className={styles.summaryRow}>
            <MetricCard
              label="资源总数"
              value={summary.resources}
              foot={`健康 ${summary.healthy} · 警告 ${summary.warning} · 严重 ${summary.critical}`}
              accent={COLORS.primary}
              hint="统计口径：拓扑中的全部节点（含宿主机 / VM / 容器 / 服务 / 任务）"
            />
            <MetricCard
              label="健康"
              value={summary.healthy}
              foot={ratioText(summary.healthy, summary.resources)}
              accent={COLORS.healthy}
            />
            <MetricCard
              label="警告"
              value={summary.warning}
              foot={ratioText(summary.warning, summary.resources)}
              accent={COLORS.warning}
            />
            <MetricCard
              label="严重"
              value={summary.critical}
              foot={summary.critical > 0 ? '需要立即处置' : '无严重资源'}
              accent={COLORS.critical}
            />
            <MetricCard
              label="任务总数"
              value={summary.tasks_total}
              foot="窗口内 agent-service 任务"
              accent={COLORS.primary}
            />
            <MetricCard
              label="任务失败"
              value={summary.tasks_failed}
              foot={ratioText(summary.tasks_failed, summary.tasks_total)}
              accent={summary.tasks_failed > 0 ? COLORS.critical : COLORS.healthy}
            />
            <MetricCard
              label="告警数"
              value={incidents.data?.count ?? summary.incidents}
              foot={`未处理 ${incidents.data?.incidents.filter((i) => i.status === 'open').length ?? summary.open_alerts} 个`}
              accent={(incidents.data?.incidents.some((i) => i.status === 'open') ?? summary.open_alerts > 0) ? COLORS.warning : COLORS.healthy}
            />
          </div>

          <VStack>
            <Panel
              title="工作负载健康"
              icon="box"
              subtitle={`${workloads.length} 个（容器 / 服务维度）`}
              extra={
                overview.loading ? <InlineLoading label="刷新中" /> : null
              }
              bodyPadding="flush"
            >
              {workloads.length === 0 ? (
                <div className={styles.empty}>当前过滤条件下没有工作负载。</div>
              ) : (
                <div className={styles.workloadGrid} style={{ padding: 12 }}>
                  {workloads.map((w) => (
                    <WorkloadCard
                      key={w.resource_id}
                      workload={w}
                      highlighted={w.resource_id === highlightResource}
                    />
                  ))}
                </div>
              )}
            </Panel>

            <Panel
              title="全局事件时间线"
              icon="clock"
              subtitle={`按层着色 · 窗口 ${windowLabel} · ${overview.data?.timeline.length ?? 0} 条`}
              bodyPadding="flush"
              footer={
                <span className="ts-inline-meta">
                  层级色：应用 / 容器 / 虚拟机 / 云平台；同一时刻的多层事件合并为一行，可直接读出因果次序
                </span>
              }
            >
              <LayerTimeline
                entries={overview.data?.timeline ?? []}
                emptyText="该时间窗内没有事件。可切换到更大的时间窗，或确认 platform / vm-agent 数据源是否可用。"
              />
            </Panel>
          </VStack>
        </>
      ) : (
        <LoadingPanel rows={4} label="加载健康总览" />
      )}
    </div>
  );
}

function ratioText(part: number, total: number): string {
  if (!total) return '—';
  return `占比 ${((part / total) * 100).toFixed(0)}%`;
}

/** 指标归一化：优先用阈值，其次用单位语义，最后用同类指标最大值。 */
function normalizeMetric(metric: WorkloadMetric, all: WorkloadMetric[]): number {
  if (metric.threshold !== undefined && metric.threshold > 0) {
    return Math.min(1, metric.value / metric.threshold);
  }
  if (metric.unit === 'ratio') return Math.min(1, metric.value);
  if (metric.unit === 'percent') return Math.min(1, metric.value / 100);
  const max = Math.max(...all.filter((m) => m.unit === metric.unit).map((m) => m.value), 1);
  return Math.min(1, metric.value / max);
}

function WorkloadCard({ workload, highlighted }: { workload: WorkloadHealth; highlighted: boolean }) {
  const metrics = workload.metrics ?? [];
  const signals = workload.signals ?? [];
  const color = STATUS_COLOR[workload.status] ?? COLORS.unknown;
  const incidentHint = workload.task_failures > 0;
  return (
    <div
      className={styles.wlCard}
      style={{
        borderLeftColor: color,
        borderColor: highlighted ? COLORS.primary : undefined,
        boxShadow: highlighted ? `inset 0 0 0 1px ${COLORS.primary}` : undefined,
      }}
    >
      <div className={styles.wlHead}>
        <Icon
          name={workload.kind === 'service' ? 'cloud' : workload.kind === 'vm' ? 'server' : 'box'}
          size={15}
          style={{ color: COLORS.inkSecondary, marginTop: 3 }}
        />
        <span className={styles.wlName}>
          <span className={styles.wlTitle}>
            {workload.name}
            {workload.workload_type ? (
              <span className="ts-inline-meta" style={{ marginLeft: 6 }}>
                {workload.workload_type}
              </span>
            ) : null}
          </span>
          <span className={styles.wlId}>{workload.resource_id}</span>
        </span>
        <span className={styles.wlScore}>
          <span className={styles.wlScoreValue} style={{ color }}>
            {workload.health_score}
          </span>
          <span className={styles.wlScoreLabel}>health</span>
        </span>
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <StatusTag status={workload.status} tiny />
        <PlainTag tiny color="var(--ts-ink-3)">
          {KIND_TEXT[workload.kind] ?? workload.kind}
        </PlainTag>
        {workload.parent ? (
          <Link
            to={`/topology?resource_id=${encodeURIComponent(workload.parent.resource_id)}`}
            className="ts-inline-meta"
          >
            ↑ {workload.parent.name}
          </Link>
        ) : null}
        {highlighted ? (
          <PlainTag tiny color={COLORS.primary}>
            当前场景焦点
          </PlainTag>
        ) : null}
      </div>

      {metrics.length ? (
        <div className={styles.wlMetrics}>
          {metrics.slice(0, 4).map((m) => {
            const pct = normalizeMetric(m, metrics);
            const mColor = STATUS_COLOR[m.status] ?? COLORS.unknown;
            return (
              <div className={styles.wlMetric} key={m.name}>
                <span className={styles.wlMetricLabel} title={m.name}>
                  {m.label}
                  {m.threshold !== undefined ? (
                    <span className="ts-inline-meta"> (阈值 {fmtValue(m.threshold, m.unit)})</span>
                  ) : null}
                </span>
                <span className={styles.wlMetricValue} style={{ color: mColor }}>
                  {fmtValue(m.value, m.unit)}{' '}
                  <span style={{ color: 'var(--ts-ink-3)', fontSize: 10 }}>
                    {m.trend === 'up' ? '↑' : m.trend === 'down' ? '↓' : '→'}
                  </span>
                </span>
                <span className={styles.wlTrack}>
                  <span className={styles.wlFill} style={{ width: `${pct * 100}%`, background: mColor }} />
                </span>
              </div>
            );
          })}
        </div>
      ) : null}

      {signals.length ? (
        <div className={styles.signalList}>
          {signals.map((s) => (
            <span className={styles.signalRow} key={s.signal}>
              <SeverityTag severity={s.severity} tiny showText={false} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.signal}</span>
              <LayerTag layer={s.layer} tiny />
              <span style={{ color: 'var(--ts-ink-3)' }}>×{s.count}</span>
              <span style={{ color: 'var(--ts-ink-3)', marginLeft: 'auto' }}>{fmtClock(s.last_at)}</span>
            </span>
          ))}
        </div>
      ) : (
        <div className="ts-inline-meta">窗口内无异常信号</div>
      )}

      <div className={styles.wlFoot}>
        <span>任务失败 {workload.task_failures}</span>
        <span>最近事件 {workload.last_event_at ? fmtClock(workload.last_event_at) : '—'}</span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
          {workload.kind === 'container' ? (
            <Link to={`/diagnosis?resource_id=${encodeURIComponent(workload.resource_id)}`}>
              诊断
            </Link>
          ) : null}
          <Link to={`/topology?resource_id=${encodeURIComponent(workload.resource_id)}`}>拓扑</Link>
        </span>
      </div>

      {incidentHint ? (
        <div className="ts-inline-meta" style={{ color: COLORS.critical }}>
          该工作负载在窗口内有失败任务，建议查看告警详情定位证据链
        </div>
      ) : null}
    </div>
  );
}
