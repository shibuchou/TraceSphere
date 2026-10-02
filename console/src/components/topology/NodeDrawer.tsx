import { useMemo } from 'react';
import { Button, Drawer, Empty } from 'antd';
import { Link } from 'react-router-dom';
import styles from './NodeDrawer.module.css';
import { Icon } from '@/components/common/Icon';
import { LayerTag, PlainTag, SeverityTag, StatusTag } from '@/components/common/Tags';
import { KIND_TEXT, STATUS_COLOR } from '@/theme/tokens';
import { fmtClockMs, fmtValue } from '@/utils/format';
import type { Incident, OverviewResponse, TimelineEntry, TopologyNode } from '@/types';

interface NodeDrawerProps {
  node: TopologyNode | null;
  onClose: () => void;
  incidents: Incident[];
  timeline: TimelineEntry[];
  /** 拓扑中的全部节点，用于反查「同一 VM / 同一服务的相关资源」 */
  allNodes: TopologyNode[];
  edges: { id: string; source: string; target: string; relation: string; label?: string }[];
  /** 从概览中取该资源的工作负载健康信息（若有） */
  overview?: OverviewResponse;
  onFocus: (id: string) => void;
}

/** 节点侧栏：节点详情 + 相关事件 + 关联告警 + 邻接资源。 */
export function NodeDrawer({
  node,
  onClose,
  incidents,
  timeline,
  allNodes,
  edges,
  overview,
  onFocus,
}: NodeDrawerProps) {
  const relatedEvents = useMemo(() => {
    if (!node) return [];
    const ids = new Set<string>([node.id, node.resource_id ?? node.id]);
    return timeline
      .filter((e) => ids.has(e.resource_id) || ids.has(e.resource_name))
      .sort((a, b) => b.observed_at.localeCompare(a.observed_at));
  }, [node, timeline]);

  const relatedIncidents = useMemo(() => {
    if (!node) return [];
    const ids = new Set<string>([node.id, node.resource_id ?? node.id, node.label]);
    return incidents.filter(
      (i) => ids.has(i.focus_resource.resource_id) || ids.has(i.focus_resource.name),
    );
  }, [node, incidents]);

  const neighbours = useMemo(() => {
    if (!node) return [];
    const byId = new Map(allNodes.map((n) => [n.id, n]));
    return edges
      .filter((e) => e.source === node.id || e.target === node.id)
      .map((e) => {
        const otherId = e.source === node.id ? e.target : e.source;
        const other = byId.get(otherId);
        return other
          ? { node: other, relation: e.relation, direction: e.source === node.id ? '出' : '入' }
          : null;
      })
      .filter((x): x is { node: TopologyNode; relation: string; direction: string } => Boolean(x));
  }, [node, allNodes, edges]);

  const workload = useMemo(() => {
    if (!node) return undefined;
    const ids = new Set<string>([node.id, node.resource_id ?? node.id]);
    return overview?.workloads.find((w) => ids.has(w.resource_id));
  }, [node, overview]);

  const title = node ? (
    <div className={styles.drawerTitle}>
      <StatusTag status={node.status} />
      <span className={styles.drawerTitleText}>
        <span className={styles.drawerName}>{node.label}</span>
        <span className={styles.drawerId}>{node.id}</span>
      </span>
    </div>
  ) : (
    '资源详情'
  );

  return (
    <Drawer
      open={Boolean(node)}
      onClose={onClose}
      width="min(560px, 100vw)"
      title={title}
      destroyOnClose
      styles={{ body: { padding: 14 }, header: { padding: '10px 14px' } }}
      extra={
        node ? (
          <Button size="small" icon={<Icon name="focus" size={13} />} onClick={() => onFocus(node.id)}>
            聚焦
          </Button>
        ) : null
      }
    >
      {node ? (
        <div className={styles.drawerBody}>
          <div>
            <div className={styles.sectionLabel}>基本信息</div>
            <div className={styles.kv} style={{ marginTop: 8 }}>
              <span className={styles.kvKey}>资源种类</span>
              <span className={styles.kvVal}>{KIND_TEXT[node.kind] ?? node.kind}</span>
              <span className={styles.kvKey}>所属层级</span>
              <span className={styles.kvVal}>{node.combo ?? '顶层（无 Combo）'}</span>
              <span className={styles.kvKey}>状态</span>
              <span className={styles.kvVal} style={{ color: STATUS_COLOR[node.status] }}>
                {node.status}
              </span>
              <span className={styles.kvKey}>关联告警</span>
              <span className={styles.kvVal}>{node.incident_count} 个</span>
              {node.subtitle ? (
                <>
                  <span className={styles.kvKey}>描述</span>
                  <span className={styles.kvVal}>{node.subtitle}</span>
                </>
              ) : null}
            </div>
          </div>

          {node.badges?.length ? (
            <div>
              <div className={styles.sectionLabel}>标记</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                {node.badges.map((b) => (
                  <PlainTag key={b} color={STATUS_COLOR[node.status] ?? 'var(--ts-ink-3)'}>
                    {b}
                  </PlainTag>
                ))}
              </div>
            </div>
          ) : null}

          {workload ? (
            <div>
              <div className={styles.sectionLabel}>
                健康分 <span style={{ color: 'var(--ts-ink-3)' }}>（展示分，不参与 RCA 评分）</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
                <span
                  className={styles.drawerName}
                  style={{ color: STATUS_COLOR[workload.status], fontFamily: 'var(--ts-mono)', fontSize: 22 }}
                >
                  {workload.health_score}
                </span>
                <span style={{ fontSize: 11, color: 'var(--ts-ink-3)' }}>/100</span>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--ts-ink-3)' }}>
                  任务失败 {workload.task_failures} 次 · 最近事件{' '}
                  {workload.last_event_at ? fmtClockMs(workload.last_event_at) : '—'}
                </span>
              </div>
            </div>
          ) : null}

          {node.metrics?.length ? (
            <div>
              <div className={styles.sectionLabel}>关键指标</div>
              <div className={styles.metricTable} style={{ marginTop: 8 }}>
                {node.metrics.map((m) => (
                  <div className={styles.metricRow} key={`${m.name}-${m.value}`}>
                    <span className={styles.metricName}>{m.name}</span>
                    <span className={styles.metricValue}>{fmtValue(m.value, m.unit)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {relatedIncidents.length ? (
            <div>
              <div className={styles.sectionLabel}>关联告警</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                {relatedIncidents.map((i) => (
                  <Link key={i.incident_id} to={`/incidents/${i.incident_id}`} className={styles.incidentRow}>
                    <SeverityTag severity={i.severity} tiny />
                    <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {i.title}
                    </span>
                    <span className={styles.incidentMeta}>
                      {i.rule} · {Math.round(i.match_score)}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ) : null}

          <div>
            <div className={styles.sectionLabel}>
              相关事件
              <span style={{ color: 'var(--ts-ink-3)' }}>（窗口内 {relatedEvents.length} 条）</span>
            </div>
            <div style={{ marginTop: 4 }}>
              {relatedEvents.length === 0 ? (
                <div className={styles.emptyHint}>
                  当前时间窗内该资源无事件。可切换到更大时间窗（健康页）或对应演示场景查看。
                </div>
              ) : (
                relatedEvents.slice(0, 20).map((e, idx) => (
                  <div className={styles.eventRow} key={`${e.signal}-${e.observed_at}-${idx}`}>
                    <span className={styles.eventTime}>{fmtClockMs(e.observed_at).slice(0, 8)}</span>
                    <span className={styles.eventBody}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                        <span className={styles.eventSignal}>{e.signal}</span>
                        <SeverityTag severity={e.severity} tiny />
                        <LayerTag layer={e.layer} tiny />
                      </span>
                      <span className={styles.eventDesc}>{e.description}</span>
                      {e.evidence_id ? (
                        <span className={styles.eventTime} style={{ display: 'inline', width: 'auto' }}>
                          {e.evidence_id}
                        </span>
                      ) : null}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div>
            <div className={styles.sectionLabel}>邻接资源（{neighbours.length}）</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 8 }}>
              {neighbours.length === 0 ? (
                <div className={styles.emptyHint}>拓扑中暂无邻接关系。</div>
              ) : (
                neighbours.map(({ node: other, relation, direction }) => (
                  <button
                    key={`${other.id}-${relation}-${direction}`}
                    type="button"
                    className={styles.incidentRow}
                    style={{ all: 'unset', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center' }}
                    onClick={() => onFocus(other.id)}
                  >
                    <PlainTag tiny color="var(--ts-ink-3)">
                      {direction} · {relation}
                    </PlainTag>
                    <StatusTag status={other.status} tiny showText={false} />
                    <span style={{ fontSize: 12 }}>{other.label}</span>
                    <span className={styles.incidentMeta}>{KIND_TEXT[other.kind]}</span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className={styles.actions}>
            {node.kind === 'container' ? (
              <Link to={`/diagnosis?resource_id=${encodeURIComponent(node.id)}`}>
                <Button size="small" type="primary" icon={<Icon name="diagnose" size={13} />}>
                  对该资源执行诊断
                </Button>
              </Link>
            ) : null}
            {relatedIncidents[0] ? (
              <Link to={`/incidents/${relatedIncidents[0].incident_id}`}>
                <Button size="small" icon={<Icon name="alert" size={13} />}>
                  查看告警详情
                </Button>
              </Link>
            ) : null}
          </div>
        </div>
      ) : (
        <Empty description="未选择资源" />
      )}
    </Drawer>
  );
}
