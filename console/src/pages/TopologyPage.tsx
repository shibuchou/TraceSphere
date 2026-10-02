import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Alert, Button, Select, Space } from 'antd';
import styles from './pages.module.css';
import { Panel, VStack } from '@/components/common/Panel';
import { Icon } from '@/components/common/Icon';
import { MetricCard, PageHead } from '@/components/common/PageHead';
import { ApiErrorState } from '@/components/common/ApiErrorState';
import { LoadingPanel } from '@/components/common/States';
import { LayerTag, PlainTag, SeverityTag, StatusTag } from '@/components/common/Tags';
import { SourceStatusStrip } from '@/components/common/DataSourceBadge';
import { NodeDrawer } from '@/components/topology/NodeDrawer';
import { TopologyGraph, type TopologyDepth, type TopologyGraphHandle } from '@/components/topology/TopologyGraph';
import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { useApp } from '@/state/AppContext';
import { COLORS, KIND_TEXT, STATUS_COLOR, STATUS_TEXT } from '@/theme/tokens';
import { fmtClock } from '@/utils/format';
import type { NodeStatus, TopologyNode } from '@/types';

const STATUS_ORDER: NodeStatus[] = ['critical', 'warning', 'healthy', 'unknown'];

export function TopologyPage() {
  const app = useApp();
  const [searchParams] = useSearchParams();
  const graphRef = useRef<TopologyGraphHandle | null>(null);

  const [depth, setDepth] = useState<TopologyDepth>(2);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true);

  const topology = useAsync((signal) => api.getTopology({ signal }), [app.refreshToken]);
  const incidents = useAsync((signal) => api.getIncidents({ signal }), [app.refreshToken]);
  const overview = useAsync((signal) => api.getOverview(900, { signal }), [app.refreshToken]);

  const scenarioResourceId = searchParams.get('resource_id') ?? app.scenario.resource_id;
  const autoFocused = useRef(false);

  const displayTopology = useMemo(() => {
    if (!topology.data) return undefined;
    const counts = new Map<string, number>();
    for (const incident of incidents.data?.incidents ?? []) {
      const resourceId = incident.focus_resource?.resource_id;
      if (resourceId) counts.set(resourceId, (counts.get(resourceId) ?? 0) + 1);
    }
    return {
      ...topology.data,
      nodes: topology.data.nodes.map((node) => {
        const incidentCount = Math.max(node.incident_count ?? 0, counts.get(node.id) ?? 0);
        return incidentCount === (node.incident_count ?? 0) ? node : { ...node, incident_count: incidentCount };
      }),
    };
  }, [topology.data, incidents.data]);

  const nodes = useMemo(() => displayTopology?.nodes ?? [], [displayTopology]);

  const findScenarioNode = (resourceId: string) => {
    const exact = nodes.find((node) => node.id === resourceId || node.resource_id === resourceId);
    if (exact) return exact;
    const prefixMatches = nodes.filter(
      (node) => node.id.startsWith(resourceId) || node.resource_id?.startsWith(resourceId),
    );
    return prefixMatches.length === 1 ? prefixMatches[0] : undefined;
  };

  const focusNode = (node: TopologyNode) => {
    if (node.kind === 'process') setDepth(3);
    else if (node.kind !== 'host' && node.kind !== 'vm') setDepth((current) => Math.max(current, 2) as TopologyDepth);
    setSelectedId(node.id);
    setDrawerOpen(true);
    window.setTimeout(() => graphRef.current?.focus(node.id), 180);
  };

  const scenarioResourceFound = Boolean(findScenarioNode(scenarioResourceId));

  useEffect(() => {
    if (!selectedId) return;
    const selected = nodes.find((node) => node.id === selectedId);
    if (!selected) return;
    const visible = selected.kind === 'process' ? depth === 3 :
      selected.kind === 'host' || selected.kind === 'vm' ? true : depth >= 2;
    if (!visible) {
      setSelectedId(null);
      setDrawerOpen(false);
    }
  }, [depth, nodes, selectedId]);

  /** 首次加载后按场景自动定位（演示路径切换时自动跟随）。 */
  useEffect(() => {
    if (autoFocused.current) return;
    if (!nodes.length) return;
    const target = findScenarioNode(scenarioResourceId);
    if (target) {
      autoFocused.current = true;
      focusNode(target);
    }
  }, [nodes, scenarioResourceId]);

  /** 场景切换后重新聚焦。 */
  useEffect(() => {
    if (!autoFocused.current) return;
    const target = findScenarioNode(scenarioResourceId);
    if (target) {
      focusNode(target);
    } else {
      setSelectedId(null);
      setDrawerOpen(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioResourceId]);

  const selectedNode: TopologyNode | null = useMemo(
    () => nodes.find((n) => n.id === selectedId) ?? null,
    [nodes, selectedId],
  );

  const incidentCounts = useMemo(() => {
    const counts: Record<NodeStatus, number> = { healthy: 0, warning: 0, critical: 0, unknown: 0 };
    for (const n of nodes) counts[n.status] += 1;
    return counts;
  }, [nodes]);

  /** 「有告警的资源」清单：直接给出可点击的排障入口。 */
  const incidentNodes = useMemo(
    () =>
      nodes
        .filter((n) => (n.incident_count ?? 0) > 0)
        .sort((a, b) => (b.incident_count ?? 0) - (a.incident_count ?? 0)),
    [nodes],
  );

  const focusOptions = useMemo(
    () =>
      nodes.map((n) => ({
        value: n.id,
        label: `${KIND_TEXT[n.kind] ?? n.kind} · ${n.label}`,
      })),
    [nodes],
  );

  const handleSelect = (node: TopologyNode | null) => {
    setSelectedId(node?.id ?? null);
    if (node) setDrawerOpen(true);
  };

  if (topology.error) {
    return (
      <div className={styles.page}>
        <PageHead
          title="资源拓扑"
          sub="GET /api/v1/topology"
          desc="ZSvirt 五层资源关系（宿主机 → 虚拟机 → 容器 → 服务 → Agent 任务），按状态着色并标注关联告警。"
        />
        <ApiErrorState error={topology.error} onRetry={topology.reload} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHead
        title="资源拓扑"
        sub="GET /api/v1/topology"
        desc="ZSvirt 五层资源关系（宿主机 → 虚拟机 → 容器 → 服务 → Agent 任务），按状态着色并标注关联告警。"
        right={
          <Space size={8} wrap>
            <Select
              size="small"
              style={{ width: 268 }}
              placeholder="聚焦某资源"
              value={selectedId ?? undefined}
              onChange={(v) => {
                const node = nodes.find((item) => item.id === v);
                if (node) focusNode(node);
              }}
              options={focusOptions}
              showSearch
            />
            <Button
              size="small"
              icon={<Icon name="refresh" size={13} />}
              onClick={() => app.refresh()}
              loading={topology.loading && !topology.data}
            >
              刷新
            </Button>
          </Space>
        }
      />

      {nodes.length > 0 && !scenarioResourceFound ? (
        <Alert
          type="info"
          showIcon
          message="当前真实数据中没有该演示场景的焦点资源"
          description="拓扑不会假装已聚焦；如需复现内置案例，请使用包含对应夹具数据的演示构建。"
          style={{ marginBottom: 12 }}
        />
      ) : null}

      <div className={styles.summaryRow}>
        <MetricCard
          label="资源总数"
          value={nodes.length}
          foot={
            topology.data
              ? `采集于 ${fmtClock(topology.data.generated_at)} UTC`
              : '正在取数…'
          }
          accent={COLORS.primary}
        />
        {STATUS_ORDER.map((s) => (
          <MetricCard
            key={s}
            label={STATUS_TEXT[s]}
            value={incidentCounts[s]}
            foot={
              s === 'critical'
                ? '需要立即处置'
                : s === 'warning'
                  ? '存在异常信号'
                  : s === 'healthy'
                    ? '无异常信号'
                    : '无数据或状态未知'
            }
            accent={STATUS_COLOR[s]}
          />
        ))}
        <MetricCard
          label="关联告警"
          value={incidents.data?.count ?? 0}
          foot={`未处理 ${incidents.data?.incidents.filter((i) => i.status === 'open').length ?? 0} 个`}
          accent={COLORS.critical}
        />
      </div>

      <div className={styles.twoCol}>
        <VStack>
          {topology.data ? (
            <TopologyGraph
              ref={graphRef}
              data={displayTopology ?? topology.data}
              depth={depth}
              onDepthChange={setDepth}
              selectedId={drawerOpen ? selectedId : null}
              onSelect={handleSelect}
              height={620}
            />
          ) : (
            <LoadingPanel rows={6} label="加载拓扑" />
          )}

          <Panel
            title="层间关系与图例"
            icon="layers"
            subtitle="API.md §4.1"
            bodyPadding="tight"
          >
            <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: 12 }}>
              <div style={{ minWidth: 200 }}>
                <div className="ts-eyebrow">层级</div>
                <div style={{ marginTop: 5, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {(topology.data?.legend ?? []).map((l) => (
                    <span key={l.kind} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <i
                        style={{
                          width: 10,
                          height: 10,
                          background: COLORS.surface,
                          border: `1px solid ${COLORS.ruleStrong}`,
                          borderRadius: 1,
                        }}
                      />
                      {l.label}
                      <span className="ts-inline-meta">{l.kind}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div style={{ minWidth: 240 }}>
                <div className="ts-eyebrow">Combo 嵌套</div>
                <div style={{ marginTop: 5, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {(topology.data?.combos ?? []).map((c) => (
                    <span key={c.id} className="ts-mono" style={{ fontSize: 11 }}>
                      {c.parent ? '└─ ' : ''}
                      {c.label}{' '}
                      <span style={{ color: COLORS.inkTertiary }}>({c.kind})</span>
                    </span>
                  ))}
                </div>
              </div>
              <div style={{ minWidth: 240 }}>
                <div className="ts-eyebrow">边关系</div>
                <div style={{ marginTop: 5, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {[...new Set((topology.data?.edges ?? []).map((e) => e.relation))].map((r) => (
                    <PlainTag key={r} tiny>
                      {r} ×{(topology.data?.edges ?? []).filter((e) => e.relation === r).length}
                    </PlainTag>
                  ))}
                </div>
              </div>
              <div style={{ minWidth: 200 }}>
                <div className="ts-eyebrow">数据来源</div>
                <div style={{ marginTop: 6 }}>
                  <SourceStatusStrip source={topology.data?.source} />
                </div>
              </div>
            </div>
          </Panel>
        </VStack>

        <VStack>
          <Panel
            title="告警资源"
            icon="alert"
            subtitle={`${incidentNodes.length} 个资源关联告警`}
            bodyPadding="tight"
            extra={
              <Link to="/incidents">
                <Button size="small" type="link">
                  全部告警
                </Button>
              </Link>
            }
          >
            <div className={styles.list} style={{ padding: 10 }}>
              {incidentNodes.length === 0 ? (
                <div className={styles.empty}>窗口内没有带告警的资源。</div>
              ) : (
                incidentNodes.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    className={`${styles.listRow} ${selectedId === n.id ? styles.listRowActive : ''}`}
                    style={{ borderLeftColor: n.incident_count ? COLORS.warning : STATUS_COLOR[n.status] }}
                    onClick={() => {
                      focusNode(n);
                    }}
                  >
                    <StatusTag status={n.status} tiny showText={false} />
                    <span className={styles.listRowTitle}>{n.label}</span>
                    <span className={styles.listRowMeta}>
                      {KIND_TEXT[n.kind] ?? n.kind} · {n.incident_count}
                    </span>
                  </button>
                ))
              )}
            </div>
          </Panel>

          <Panel title="最近事件" icon="clock" subtitle="窗口 15m" bodyPadding="tight">
            <div style={{ padding: '6px 10px 10px' }}>
              {overview.data ? (
                [...overview.data.timeline]
                  .sort((a, b) => b.observed_at.localeCompare(a.observed_at))
                  .slice(0, 8)
                  .map((e, idx) => (
                    <div
                      key={`${e.signal}-${e.observed_at}-${idx}`}
                      style={{ padding: '6px 0', borderBottom: '1px dotted var(--ts-rule)' }}
                    >
                      <div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span className="ts-inline-meta">{fmtClock(e.observed_at)}</span>
                        <span className="ts-mono" style={{ fontSize: 11.5, fontWeight: 600 }}>
                          {e.signal}
                        </span>
                        <SeverityTag severity={e.severity} tiny />
                        <LayerTag layer={e.layer} tiny />
                      </div>
                      <div style={{ fontSize: 11.5, color: 'var(--ts-ink-2)' }}>{e.description}</div>
                    </div>
                  ))
              ) : overview.error ? (
                <div className={styles.empty}>{overview.error.message}</div>
              ) : (
                <LoadingPanel rows={3} label="加载事件" />
              )}
            </div>
          </Panel>

          <Panel title="演示提示" icon="info" bodyPadding="tight">
            <div style={{ fontSize: 12, color: 'var(--ts-ink-2)', padding: '4px 2px', lineHeight: 1.7 }}>
              <p style={{ margin: '0 0 6px' }}>
                顶栏「演示路径」可在四个场景（OOM、CPU、工具失败、GPU 显存耗尽）之间一键切换，拓扑会自动聚焦到
                该场景的焦点资源（当前：
                <span className="ts-mono"> {app.scenario.resource_id}</span>）。
              </p>
              <p style={{ margin: 0 }}>
                层级切换 <b>L1</b> 只看云平台骨架，<b>L2</b> 展开工作负载，<b>L3</b> 追加进程层（若采集到）。
                资源种类过滤会把跨 Combo 的同类资源并排对比。
              </p>
            </div>
          </Panel>
        </VStack>
      </div>

      <NodeDrawer
        node={drawerOpen ? selectedNode : null}
        onClose={() => setDrawerOpen(false)}
        incidents={incidents.data?.incidents ?? []}
        timeline={overview.data?.timeline ?? []}
        allNodes={nodes}
        edges={topology.data?.edges ?? []}
        overview={overview.data}
        onFocus={(id) => {
          const node = nodes.find((item) => item.id === id);
          if (node) focusNode(node);
        }}
      />
    </div>
  );
}
