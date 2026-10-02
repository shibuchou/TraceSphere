import { useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { App as AntdApp, Button, Descriptions, Space, Tooltip } from 'antd';
import styles from './pages.module.css';
import { Panel, VStack } from '@/components/common/Panel';
import { Icon } from '@/components/common/Icon';
import { MetricCard, PageHead } from '@/components/common/PageHead';
import { LoadingPanel } from '@/components/common/States';
import { ApiErrorState } from '@/components/common/ApiErrorState';
import { IncidentStatusTag, PlainTag, SeverityTag, StatusTag } from '@/components/common/Tags';
import { SourceStatusStrip } from '@/components/common/DataSourceBadge';
import { EvidenceList } from '@/components/evidence/EvidenceList';
import { LayerTimeline } from '@/components/timeline/LayerTimeline';
import { CandidateList, DimensionBars, MatchScoreHeader } from '@/components/diagnosis/ScoreBreakdown';
import { TopologyGraph, subGraphToTopology, type TopologyGraphHandle } from '@/components/topology/TopologyGraph';
import { MetricSeriesPanel } from '@/components/metrics/MetricCharts';
import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { useApp } from '@/state/AppContext';
import { COLORS, KIND_TEXT, SEVERITY_TEXT } from '@/theme/tokens';
import { fmtClock, fmtDateTime } from '@/utils/format';
import type { Diagnosis, Suggestion } from '@/types';

export function IncidentDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const app = useApp();
  const { message } = AntdApp.useApp();
  const graphRef = useRef<TopologyGraphHandle | null>(null);
  const [statusBusy, setStatusBusy] = useState(false);

  const detail = useAsync((signal) => api.getIncident(id, { signal }), [id, app.refreshToken]);

  async function changeStatus(action: 'silence' | 'acknowledge' | 'resolve' | 'open') {
    setStatusBusy(true);
    try {
      await api.setIncidentStatus(id, action);
      message.success(
        action === 'silence' ? '已静默' : action === 'acknowledge' ? '已确认' : action === 'resolve' ? '已标记处理' : '已恢复',
      );
      app.refresh();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setStatusBusy(false);
    }
  }

  const focusResource = detail.data?.incident.focus_resource;
  const metrics = useAsync(
    (signal) => api.getMetricsSeries(focusResource?.resource_id ?? '', 900, { signal }),
    [focusResource?.resource_id, app.refreshToken],
    { enabled: Boolean(focusResource?.resource_id) && focusResource?.kind === 'container' },
  );

  const highlightIds = useMemo(() => detail.data?.diagnosis?.evidence_ids ?? [], [detail.data]);

  if (detail.error && !detail.data) {
    return (
      <div className={styles.page}>
        <PageHead title="告警详情" sub={`GET /api/v1/incidents/${id}`} desc="证据链 → 诊断 → 影响范围。" />
        <ApiErrorState
          error={detail.error}
          onRetry={detail.reload}
          extra={
            <Link to="/incidents">
              <Button size="small">返回告警列表</Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (!detail.data) {
    return (
      <div className={styles.page}>
        <PageHead title="告警详情" sub={`GET /api/v1/incidents/${id}`} />
        <LoadingPanel rows={7} label="加载告警详情" />
      </div>
    );
  }

  const { incident, impact, graph, window: win } = detail.data;
  const diagnosis = detail.data.diagnosis;
  const candidates = detail.data.candidates ?? [];
  const evidence = detail.data.evidence ?? [];
  const timeline = detail.data.timeline ?? [];
  const impactScope = impact.scope ?? [];
  const graphNodes = graph.nodes ?? [];
  const graphEdges = graph.edges ?? [];
  const diagnosisHref = incident.correlation_id
    ? `/diagnosis?correlation_id=${encodeURIComponent(incident.correlation_id)}`
    : incident.focus_resource?.resource_id
      ? `/diagnosis?resource_id=${encodeURIComponent(incident.focus_resource.resource_id)}`
      : '/diagnosis';
  const statusColor = incident.severity === 'critical' ? COLORS.critical : COLORS.warning;

  return (
    <div className={styles.page}>
      <PageHead
        title={incident.title}
        sub={`GET /api/v1/incidents/${incident.incident_id}`}
        desc={incident.summary}
        right={
          <Space size={8} wrap>
            {incident.status === 'silenced' ? (
              <Button size="small" loading={statusBusy} onClick={() => changeStatus('open')}>
                取消静默
              </Button>
            ) : (
              <Button size="small" loading={statusBusy} onClick={() => changeStatus('silence')}>
                静默
              </Button>
            )}
            {incident.status === 'open' ? (
              <Button size="small" loading={statusBusy} onClick={() => changeStatus('acknowledge')}>
                确认
              </Button>
            ) : null}
            {incident.status !== 'resolved' ? (
              <Button size="small" loading={statusBusy} onClick={() => changeStatus('resolve')}>
                标记已处理
              </Button>
            ) : null}
            <Link to="/incidents">
              <Button size="small" icon={<Icon name="chevron" size={12} style={{ transform: 'rotate(180deg)' }} />}>
                告警列表
              </Button>
            </Link>
            <Link to={diagnosisHref}>
              <Button size="small" type="primary" icon={<Icon name="diagnose" size={13} />}>
                重新诊断
              </Button>
            </Link>
            <Link to={`/topology?resource_id=${encodeURIComponent(incident.focus_resource.resource_id)}`}>
              <Button size="small" icon={<Icon name="topology" size={13} />}>
                在拓扑中查看
              </Button>
            </Link>
          </Space>
        }
        footer={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 6 }}>
            <SeverityTag severity={incident.severity} />
            <IncidentStatusTag status={incident.status} />
            <PlainTag color="var(--ts-ink-secondary)">{incident.rule}</PlainTag>
            <PlainTag color="var(--ts-ink-3)">corr {incident.correlation_id || '—'}</PlainTag>
            <span className="ts-inline-meta">
              {fmtDateTime(win.from)} → {fmtDateTime(win.to)} UTC
            </span>
            <SourceStatusStrip source={detail.data.source} />
          </div>
        }
      />

      <div className={styles.summaryRow}>
        <MetricCard label="证据条数" value={incident.evidence_count} accent={COLORS.primary} foot={`展示 ${evidence.length} 条`} />
        <MetricCard label="影响任务" value={incident.affected_tasks} accent={statusColor} foot={impact.counts.tasks ? '含子任务' : '无任务受影响'} />
        <MetricCard
          label="Top-1 评分"
          value={diagnosis ? Math.round(diagnosis.match_score) : '—'}
          accent={COLORS.critical}
          foot={diagnosis ? 'Evidence Match（非概率）' : '暂无匹配诊断'}
        />
        <MetricCard label="候选数" value={candidates.length} accent={COLORS.primary} foot="按评分降序" />
        <MetricCard
          label="首次发现"
          value={fmtClock(incident.first_seen_at)}
          accent={COLORS.warning}
          foot={fmtDateTime(incident.first_seen_at)}
        />
        <MetricCard
          label="最近更新"
          value={fmtClock(incident.last_seen_at)}
          accent={COLORS.warning}
          foot={fmtDateTime(incident.last_seen_at)}
        />
      </div>

      <VStack>
        <Panel
          title="事件摘要"
          icon="alert"
          subtitle="关联簇事实 + Top-1 诊断"
          extra={
            <Tooltip title="Evidence Match 为规则证据命中评分，不表示发生概率">
              <span className="ts-inline-meta">评分口径说明</span>
            </Tooltip>
          }
        >
          {diagnosis ? (
            <>
              <MatchScoreHeader diagnosis={diagnosis} />
              <div style={{ marginTop: 14 }}>
                <div className="ts-eyebrow" style={{ marginBottom: 6 }}>
                  五维度明细（方案 §6.3）
                </div>
                <DimensionBars items={diagnosis.score_breakdown ?? []} />
              </div>
            </>
          ) : (
            <div className={styles.empty}>
              当前告警没有匹配到可展示的根因诊断。证据、时间线和影响范围仍可用于人工排查。
            </div>
          )}
          <Descriptions
            size="small"
            bordered
            column={{ xs: 1, sm: 2, md: 3 }}
            style={{ marginTop: 14 }}
            items={[
              {
                key: 'focus',
                label: '重点资源',
                children: (
                  <span className="ts-mono">
                    {incident.focus_resource?.name ?? '未知资源'}
                    <br />
                    <span style={{ color: 'var(--ts-ink-3)' }}>{incident.focus_resource?.resource_id ?? '—'}</span>
                  </span>
                ),
              },
              {
                key: 'root',
                label: '根因标识',
                children: diagnosis ? <span className="ts-mono">{diagnosis.root_cause}</span> : '—',
              },
              {
                key: 'label',
                label: '根因说明',
                children: diagnosis?.root_cause_label ?? '暂无匹配诊断',
              },
              {
                key: 'source',
                label: '关联簇来源',
                children: <span className="ts-mono">{incident.source}</span>,
              },
              {
                key: 'window',
                label: '关联时间窗',
                children: (
                  <span className="ts-mono">
                    {fmtDateTime(win.from)} → {fmtDateTime(win.to)}
                  </span>
                ),
              },
              {
                key: 'severity',
                label: '规则严重度',
                children: diagnosis
                  ? `${SEVERITY_TEXT[diagnosis.severity] ?? diagnosis.severity}（${diagnosis.severity}）`
                  : '—',
              },
            ]}
          />
        </Panel>

        <Panel
          title="证据列表"
          icon="evidence"
          subtitle={`${evidence.length} 条 · 命中 TOP-1 的证据以 ★ 标注`}
          bodyPadding="flush"
          extra={<span className="ts-inline-meta">点击任一条展开原始 payload</span>}
        >
          <EvidenceList items={evidence} highlightIds={highlightIds} />
        </Panel>

        <Panel
          title="处置建议"
          icon="rule"
          subtitle={diagnosis ? `来自规则 ${diagnosis.rule}@v${diagnosis.rule_version} 的 result.suggestions` : '暂无规则处置建议'}
          bodyPadding="flush"
        >
          {diagnosis ? (
            <SuggestionList suggestions={diagnosis.suggestions ?? []} fallback={diagnosis.rule} />
          ) : (
            <div className={styles.empty}>服务端未返回匹配规则的处置建议。</div>
          )}
        </Panel>

        <div className={styles.twoCol}>
          <Panel title="分层时间线" icon="clock" subtitle={`${timeline.length} 条事件`} bodyPadding="flush">
            <LayerTimeline
              entries={timeline}
              incidentId={incident.incident_id}
              emptyText="该告警没有附带时间线。"
            />
          </Panel>

          <VStack>
            <Panel
              title="影响范围"
              icon="layers"
              subtitle={`任务 ${impact.counts.tasks ?? 0} · 服务 ${impact.counts.services ?? 0} · 容器 ${impact.counts.containers ?? 0}`}
              bodyPadding="tight"
            >
              <div className={styles.impactList} style={{ marginTop: 6 }}>
                {impactScope.length === 0 ? (
                  <div className={styles.empty}>未识别到受影响资源。</div>
                ) : (
                  impactScope.map((item) => (
                    <div className={styles.impactRow} key={`${item.resource_id}-${item.relation}`}>
                      <span className={styles.depthChip}>depth {item.depth}</span>
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
                          <StatusTag status={item.status} tiny showText={false} />
                          <span style={{ fontWeight: 600 }}>{item.name}</span>
                          <PlainTag tiny color="var(--ts-ink-3)">
                            {KIND_TEXT[item.kind] ?? item.kind} · {item.relation}
                          </PlainTag>
                        </span>
                        <span className="ts-inline-meta" style={{ display: 'block', marginTop: 2 }}>
                          {item.resource_id}
                        </span>
                        {item.detail ? (
                          <span style={{ fontSize: 11.5, color: 'var(--ts-ink-2)' }}>{item.detail}</span>
                        ) : null}
                      </span>
                      <Link to={`/topology?resource_id=${encodeURIComponent(item.resource_id)}`}>
                        <Button size="small" type="link">
                          拓扑
                        </Button>
                      </Link>
                    </div>
                  ))
                )}
              </div>
            </Panel>

            {candidates.length > 1 ? (
              <Panel title="备选候选" icon="diagnose" subtitle="Top-N 排序语义" bodyPadding="tight">
                <div style={{ marginTop: 6 }}>
                  <CandidateList candidates={candidates} currentRule={diagnosis?.rule} />
                </div>
              </Panel>
            ) : null}
          </VStack>
        </div>

        <Panel
          title="相关资源子图"
          icon="topology"
          subtitle={`${graphNodes.length} 个节点 · ${graphEdges.length} 条边`}
          bodyPadding="flush"
          extra={
            <Button
              size="small"
              icon={<Icon name="fit" size={13} />}
              onClick={() => graphRef.current?.fit()}
              disabled={graphNodes.length === 0}
            >
              适应画布
            </Button>
          }
        >
          {graphNodes.length === 0 ? (
            <div className={styles.empty}>
              服务端未返回子图（诊断服务未启用 graph 生成时会省略该字段）。可切换到拓扑页查看完整资源关系。
            </div>
          ) : (
            <TopologyGraph
              ref={graphRef}
              data={subGraphToTopology({ nodes: graphNodes, edges: graphEdges })}
              depth={2}
              height={380}
              compact
            />
          )}
        </Panel>

        <Panel
          title="指标曲线"
          icon="pulse"
          subtitle={
            focusResource?.kind === 'container'
              ? `GET /api/v1/metrics/series?resource_id=${focusResource.resource_id}`
              : '仅容器类资源提供曲线'
          }
          bodyPadding="default"
        >
          {focusResource?.kind !== 'container' ? (
            <div className={styles.empty}>
              焦点资源为 {KIND_TEXT[focusResource?.kind ?? 'unknown'] ?? '未知类型'}
              ，不提供容器级指标曲线。可切换到其承载容器查看。
            </div>
          ) : metrics.error ? (
            <div className={styles.empty}>
              {metrics.error.message}（{metrics.error.hint}）
            </div>
          ) : metrics.data ? (
            <MetricSeriesPanel data={metrics.data} />
          ) : (
            <LoadingPanel rows={3} label="加载指标曲线" />
          )}
        </Panel>
      </VStack>
    </div>
  );
}

/** 处置建议：每条强制展示 依据 / 操作 / 风险 三段（方案 §6.3）。 */
export function SuggestionList({
  suggestions,
  fallback,
}: {
  suggestions: Suggestion[];
  fallback?: string;
}) {
  if (suggestions.length === 0) {
    return (
      <div className={styles.empty}>
        该规则未定义处置建议（result.suggestions 为空）。请检查规则文件
        {fallback ? ` ${fallback}.yaml` : ''} 的 result 段。
      </div>
    );
  }
  return (
    <div className={styles.subList} style={{ padding: 12 }}>
      {suggestions.map((s, idx) => (
        <div className={styles.suggestion} key={`${s.action}-${idx}`}>
          <div className={styles.suggestionHead}>
            <span
              className="ts-mono"
              style={{
                width: 18,
                height: 18,
                borderRadius: 2,
                background: COLORS.primarySoft,
                color: COLORS.primary,
                fontSize: 11,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 600,
              }}
            >
              {idx + 1}
            </span>
            <span className={styles.suggestionTitle}>{s.title}</span>
            <span className={styles.suggestionAction}>{s.action}</span>
          </div>
          <div className={styles.suggRow}>
            <span className={`${styles.suggKey} ${styles.suggKeyBasis}`}>依据</span>
            <span className={styles.suggVal}>{s.basis}</span>
          </div>
          <div className={styles.suggRow}>
            <span className={`${styles.suggKey} ${styles.suggKeyDetail}`}>操作</span>
            <span className={styles.suggVal}>{s.detail}</span>
          </div>
          <div className={styles.suggRow}>
            <span className={`${styles.suggKey} ${styles.suggKeyRisk}`}>风险</span>
            <span className={styles.suggVal}>{s.risk}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function scoreColor(d: Diagnosis): string {
  return d.match_score >= 80 ? COLORS.critical : d.match_score >= 55 ? COLORS.warning : COLORS.unknown;
}
