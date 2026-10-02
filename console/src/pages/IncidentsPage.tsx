import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Button, Input, Segmented, Select, Space, Table, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import styles from './pages.module.css';
import { Panel } from '@/components/common/Panel';
import { Icon } from '@/components/common/Icon';
import { MetricCard, PageHead } from '@/components/common/PageHead';
import { LoadingPanel } from '@/components/common/States';
import { ApiErrorState } from '@/components/common/ApiErrorState';
import { IncidentStatusTag, LayerTag, PlainTag, SeverityTag } from '@/components/common/Tags';
import { SourceStatusStrip } from '@/components/common/DataSourceBadge';
import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { useApp } from '@/state/AppContext';
import { SCENARIOS } from '@/data/scenarios';
import { COLORS, SEVERITY_TEXT } from '@/theme/tokens';
import { fmtClock, fmtDateTime } from '@/utils/format';
import type { Incident, Severity } from '@/types';

const SEVERITY_RANK: Record<Severity, number> = { critical: 0, major: 1, warning: 2, info: 3 };
const WINDOWS = [
  { label: '15 分钟', seconds: 900 },
  { label: '1 小时', seconds: 3600 },
  { label: '6 小时', seconds: 21600 },
  { label: '24 小时', seconds: 86400 },
];

export function IncidentsPage() {
  const app = useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const resourceFilter = searchParams.get('resource_id') ?? '';
  const [severity, setSeverity] = useState<Severity[]>([]);
  const [rule, setRule] = useState<string | 'all'>('all');
  const [windowSeconds, setWindowSeconds] = useState(86400);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open'>('all');

  const incidents = useAsync((signal) => api.getIncidents({ signal }), [app.refreshToken]);

  const highlightIncident = SCENARIOS.find(
    (s) => s.resource_id === (searchParams.get('resource_id') ?? app.scenario.resource_id),
  )?.incident_id;

  const rows = useMemo(() => {
    const list = incidents.data?.incidents ?? [];
    const fromMs = Date.now() - windowSeconds * 1000;
    const filtered = list.filter((i) => {
      if (severity.length && !severity.includes(i.severity)) return false;
      if (rule !== 'all' && i.rule !== rule) return false;
      if (statusFilter === 'open' && i.status !== 'open') return false;
      if (resourceFilter && i.focus_resource.resource_id !== resourceFilter) return false;
      // 时间窗按 last_seen_at 判定（与后端 rule_scan 的窗口语义一致）
      if (windowSeconds < 86400 && new Date(i.last_seen_at).getTime() < fromMs) return false;
      if (keyword) {
        const k = keyword.toLowerCase();
        const haystack = `${i.incident_id} ${i.correlation_id ?? ''} ${i.title} ${i.rule} ${i.summary} ${i.focus_resource.name}`.toLowerCase();
        if (!haystack.includes(k)) return false;
      }
      return true;
    });
    return filtered.sort(
      (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.match_score - a.match_score,
    );
  }, [incidents.data, severity, rule, windowSeconds, keyword, statusFilter, resourceFilter]);

  const ruleOptions = useMemo(() => {
    const set = new Set((incidents.data?.incidents ?? []).map((i) => i.rule));
    return [
      { label: `全部规则 (${incidents.data?.incidents.length ?? 0})`, value: 'all' },
      ...[...set].map((r) => ({
        label: `${r} (${(incidents.data?.incidents ?? []).filter((i) => i.rule === r).length})`,
        value: r,
      })),
    ];
  }, [incidents.data]);

  const counts = useMemo(() => {
    const list = incidents.data?.incidents ?? [];
    return {
      total: list.length,
      critical: list.filter((i) => i.severity === 'critical').length,
      major: list.filter((i) => i.severity === 'major').length,
      open: list.filter((i) => i.status === 'open').length,
      tasks: list.reduce((acc, i) => acc + i.affected_tasks, 0),
    };
  }, [incidents.data]);

  const columns: ColumnsType<Incident> = [
    {
      title: '严重度',
      dataIndex: 'severity',
      width: 92,
      sorter: (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity],
      render: (value: Severity) => <SeverityTag severity={value} />,
    },
    {
      title: '规则 / 标题',
      dataIndex: 'title',
      render: (_: string, row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Link to={`/incidents/${row.incident_id}`} style={{ fontWeight: 600, fontSize: 12.5 }}>
            {row.title}
            {row.incident_id === highlightIncident ? (
              <PlainTag tiny color={COLORS.primary}>
                当前场景
              </PlainTag>
            ) : null}
          </Link>
          <span className="ts-inline-meta">
            {row.rule} · {row.incident_id} · corr {row.correlation_id || '—'}
          </span>
          <span style={{ fontSize: 11.5, color: 'var(--ts-ink-2)' }}>{row.summary}</span>
        </div>
      ),
    },
    {
      title: '重点资源',
      dataIndex: 'focus_resource',
      width: 200,
      render: (_: unknown, row) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <i
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                border: `1.6px solid ${row.severity === 'critical' ? COLORS.critical : COLORS.warning}`,
                flex: 'none',
              }}
            />
            <span style={{ fontSize: 12 }}>{row.focus_resource.name}</span>
          </span>
          <span className="ts-inline-meta">{row.focus_resource.resource_id}</span>
        </div>
      ),
    },
    {
      title: 'Evidence Match',
      dataIndex: 'match_score',
      width: 132,
      defaultSortOrder: 'descend',
      sorter: (a, b) => a.match_score - b.match_score,
      render: (value: number) => (
        <Tooltip title="规则证据命中评分（0–100），非概率">
          <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span
              className="ts-mono"
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: value >= 80 ? COLORS.critical : value >= 55 ? COLORS.warning : COLORS.inkSecondary,
              }}
            >
              {Math.round(value)}
            </span>
            <span
              style={{
                flex: 1,
                height: 5,
                background: '#eef1f4',
                border: '1px solid var(--ts-rule)',
                borderRadius: 1,
                overflow: 'hidden',
                minWidth: 44,
              }}
            >
              <span
                style={{ display: 'block', height: '100%', width: `${value}%`, background: COLORS.primary }}
              />
            </span>
          </span>
        </Tooltip>
      ),
    },
    {
      title: '影响任务',
      dataIndex: 'affected_tasks',
      width: 88,
      sorter: (a, b) => a.affected_tasks - b.affected_tasks,
      render: (value: number, row) => (
        <span className="ts-mono" style={{ fontSize: 12 }}>
          {value}
          <span style={{ color: 'var(--ts-ink-3)', fontSize: 10 }}> / {row.evidence_count} 证据</span>
        </span>
      ),
    },
    {
      title: '首次 / 最近',
      dataIndex: 'first_seen_at',
      width: 168,
      sorter: (a, b) => a.first_seen_at.localeCompare(b.first_seen_at),
      render: (_: string, row) => (
        <span className="ts-mono" style={{ fontSize: 11 }}>
          <span title={`首次 ${fmtDateTime(row.first_seen_at)}`}>{fmtClock(row.first_seen_at)}</span>
          <br />
          <span style={{ color: 'var(--ts-ink-3)' }} title={`最近 ${fmtDateTime(row.last_seen_at)}`}>
            → {fmtClock(row.last_seen_at)}
          </span>
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 96,
      render: (_: string, row) => (
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <IncidentStatusTag status={row.status} />
          <span className="ts-inline-meta">{row.source}</span>
        </span>
      ),
    },
    {
      title: '',
      key: 'action',
      width: 74,
      render: (_: unknown, row) => (
        <Link to={`/incidents/${row.incident_id}`}>
          <Button size="small" type="link">
            详情
          </Button>
        </Link>
      ),
    },
  ];

  if (incidents.error && !incidents.data) {
    return (
      <div className={styles.page}>
        <PageHead title="告警" sub="GET /api/v1/incidents" desc="关联簇 + Top-1 诊断摘要。" />
        <ApiErrorState error={incidents.error} onRetry={incidents.reload} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHead
        title="告警"
        sub="GET /api/v1/incidents"
        desc="每条告警对应一个关联簇及其 Top-1 诊断结论。Evidence Match 是规则证据命中评分，用于排序与取舍，不是概率。"
        right={
          <Space size={8} wrap>
            <Input
              size="small"
              allowClear
              placeholder="搜索 incident_id / correlation_id / 标题"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              style={{ width: 260 }}
              prefix={<Icon name="search" size={13} style={{ color: 'var(--ts-ink-3)' }} />}
            />
            <Button
              size="small"
              icon={<Icon name="refresh" size={13} />}
              onClick={() => app.refresh()}
              loading={incidents.loading && !incidents.data}
            >
              刷新
            </Button>
          </Space>
        }
        footer={
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginTop: 6 }}>
            <span className="ts-inline-meta">
              共 {counts.total} 条 · 严重 {counts.critical} · 重要 {counts.major} · 未处理 {counts.open}
            </span>
            <SourceStatusStrip source={incidents.data?.source} />
          </div>
        }
      />

      <div className={styles.summaryRow}>
        <MetricCard label="告警总数" value={counts.total} accent={COLORS.primary} foot="关联簇 + 规则扫描" />
        <MetricCard label="严重" value={counts.critical} accent={COLORS.critical} foot="需立即处置" />
        <MetricCard label="重要" value={counts.major} accent={COLORS.warning} foot="需当日跟进" />
        <MetricCard label="未处理" value={counts.open} accent={counts.open ? COLORS.critical : COLORS.healthy} foot="open 状态" />
        <MetricCard label="受影响任务" value={counts.tasks} accent={COLORS.primary} foot="跨告警去重前" />
      </div>

      <div className={styles.toolbar} style={{ gap: 12 }}>
        <span className="ts-eyebrow">过滤</span>
        {resourceFilter ? (
          <Button
            size="small"
            type="default"
            onClick={() => {
              const params = new URLSearchParams(searchParams);
              params.delete('resource_id');
              setSearchParams(params, { replace: true });
            }}
            title={resourceFilter}
          >
            资源筛选已启用 · 清除
          </Button>
        ) : null}
        <Segmented
          size="small"
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as 'all' | 'open')}
          options={[
            { label: '全部状态', value: 'all' },
            { label: '仅未处理', value: 'open' },
          ]}
        />
        <Select
          size="small"
          mode="multiple"
          allowClear
          placeholder="严重度（默认全部）"
          style={{ width: 200 }}
          value={severity}
          onChange={(v) => setSeverity(v as Severity[])}
          options={(['critical', 'major', 'warning', 'info'] as Severity[]).map((s) => ({
            label: `${SEVERITY_TEXT[s]}（${(incidents.data?.incidents ?? []).filter((i) => i.severity === s).length}）`,
            value: s,
          }))}
        />
        <Select
          size="small"
          style={{ width: 190 }}
          value={rule}
          onChange={setRule}
          options={ruleOptions}
        />
        <Select
          size="small"
          style={{ width: 130 }}
          value={windowSeconds}
          onChange={setWindowSeconds}
          options={WINDOWS.map((w) => ({ label: `最近 ${w.label}`, value: w.seconds }))}
        />
        <span className="ts-inline-meta">
          命中 {rows.length} / {incidents.data?.count ?? 0} 条
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <LayerTag layer="application" tiny />
          <span className="ts-inline-meta">时间窗按 last_seen_at 过滤</span>
        </span>
      </div>

      {incidents.loading && !incidents.data ? (
        <LoadingPanel rows={6} label="加载告警列表" />
      ) : (
        <Panel title="告警列表" icon="alert" subtitle={`${rows.length} 条`} bodyPadding="flush">
          <Table<Incident>
            rowKey="incident_id"
            size="small"
            columns={columns}
            dataSource={rows}
            pagination={{ pageSize: 12, size: 'small', showSizeChanger: false, hideOnSinglePage: true }}
            locale={{
              emptyText: (
                <div className={styles.empty}>
                  没有符合过滤条件的告警。可放宽严重度 / 规则 / 时间窗，或确认诊断服务是否已采集到关联簇。
                </div>
              ),
            }}
            scroll={{ x: 1120 }}
          />
        </Panel>
      )}
    </div>
  );
}
