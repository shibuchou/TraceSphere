import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef } from 'react';
import { Graph, idOf } from '@antv/g6';
import type { GraphData, IElementEvent } from '@antv/g6';
import { Button, Segmented, Select, Tooltip } from 'antd';
import styles from './TopologyGraph.module.css';
import { Icon } from '@/components/common/Icon';
import { COLORS, KIND_TEXT, MONO_FONT, SANS_FONT, STATUS_COLOR, STATUS_TEXT } from '@/theme/tokens';
import type { NodeStatus, ResourceKind, SubGraph, TopologyEdge, TopologyNode, TopologyResponse } from '@/types';

export type TopologyDepth = 1 | 2 | 3;

export interface TopologyGraphHandle {
  fit: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  focus: (id: string) => void;
}

export interface TopologyGraphProps {
  data: Pick<TopologyResponse, 'nodes' | 'edges'> & Partial<Pick<TopologyResponse, 'combos' | 'legend'>>;
  depth?: TopologyDepth;
  onDepthChange?: (depth: TopologyDepth) => void;
  selectedId?: string | null;
  onSelect?: (node: TopologyNode | null) => void;
  /** 隐藏内置工具条（详情页内嵌子图时使用） */
  compact?: boolean;
  height?: number;
  /** 空态提示 */
  emptyHint?: string;
  className?: string;
}

/** 展示层级顺序（左 → 右即 宿主机 → 虚拟机 → 容器 → 服务 → 任务 → 进程）。 */
const FLOW_KIND_ORDER: ResourceKind[] = ['host', 'vm', 'container', 'service', 'task', 'process'];
const KIND_ORDER: ResourceKind[] = [
  ...FLOW_KIND_ORDER,
  'gpu',
  'cluster',
  'zone',
  'network',
  'datastore',
  'image',
  'offering',
  'volume',
];
const COLUMN_WIDTH = 250;
const ROW_GAP = 74;
const PAD = 40;
const ORPHAN_COLUMNS = 3;

const EMPTY_COMBO = 'combo:__none__';

interface Placement {
  x: number;
  y: number;
  w: number;
  h: number;
}

function nodeSize(kind: ResourceKind): { w: number; h: number } {
  switch (kind) {
    case 'host':
      return { w: 176, h: 56 };
    case 'vm':
      return { w: 196, h: 62 };
    case 'service':
      return { w: 168, h: 54 };
    case 'task':
      return { w: 208, h: 50 };
    case 'process':
      return { w: 150, h: 40 };
    default:
      return { w: 182, h: 56 };
  }
}

function isVisibleAt(kind: ResourceKind, depth: TopologyDepth): boolean {
  if (kind === 'host' || kind === 'vm') return true;
  if (kind === 'container' || kind === 'service' || kind === 'task') return depth >= 2;
  if (kind === 'process') return depth >= 3;
  return depth >= 2;
}

/**
 * 层级泳道布局（确定性）：
 * 1. 按 kind 分配列（同一资源深度恒定，避免边交叉）；
 * 2. 以 combo（含嵌套的 host → vm）为分组，组内取最大行数决定该组高度；
 * 3. 组按 VM 垂直堆叠，组内每一行按列定位，行内左对齐。
 * 4. Combo 自身的位置由 G6 依据子元素包围盒推算，故此处只需算出叶子节点坐标。
 */
export function computeLayout(
  nodes: TopologyNode[],
  depth: TopologyDepth,
  comboParent: Record<string, string | null>,
  options: { allCombos?: boolean; kindFilter?: ResourceKind | 'all' } = {},
): {
  placements: Map<string, Placement>;
  nodesByCombo: Map<string, TopologyNode[]>;
} {
  const { allCombos = false, kindFilter = 'all' } = options;
  const visible = nodes.filter(
    (n) => isVisibleAt(n.kind, depth) && (kindFilter === 'all' || n.kind === kindFilter),
  );
  const placements = new Map<string, Placement>();
  const nodesByCombo = new Map<string, TopologyNode[]>();

  for (const n of visible) {
    const comboIsKnown = Boolean(n.combo && Object.prototype.hasOwnProperty.call(comboParent, n.combo));
    const isFlowNode = FLOW_KIND_ORDER.includes(n.kind);
    const key = !allCombos && isFlowNode && comboIsKnown ? n.combo as string : EMPTY_COMBO;
    const list = nodesByCombo.get(key);
    if (list) list.push(n);
    else nodesByCombo.set(key, [n]);
  }

  // combo 顺序：先 VM（其 id 出现在其它 combo 的 parent 之外的），保持输入顺序稳定
  const combos = [...nodesByCombo.keys()].filter((k) => k !== EMPTY_COMBO);
  const rank = (comboId: string): number => {
    let r = 0;
    let cur: string | null | undefined = comboParent[comboId] ?? null;
    let guard = 0;
    while (cur && guard < 8) {
      r += 1;
      cur = comboParent[cur] ?? null;
      guard += 1;
    }
    return r;
  };
  combos.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));

  const groups: { comboId: string; nodes: TopologyNode[] }[] = combos.map((id) => ({
    comboId: id,
    nodes: nodesByCombo.get(id) ?? [],
  }));
  const orphan = nodesByCombo.get(EMPTY_COMBO);
  if (orphan?.length) groups.push({ comboId: EMPTY_COMBO, nodes: orphan });

  let cursorY = PAD;
  for (const group of groups) {
    if (group.comboId === EMPTY_COMBO) {
      // Unattached and platform-side resources share a compact grid instead of
      // forming a tall first column or a bogus Combo for a missing parent.
      const ordered = [...group.nodes].sort((a, b) => {
        const ai = KIND_ORDER.indexOf(a.kind);
        const bi = KIND_ORDER.indexOf(b.kind);
        return (ai < 0 ? KIND_ORDER.length : ai) - (bi < 0 ? KIND_ORDER.length : bi) || a.label.localeCompare(b.label);
      });
      const columns = Math.min(ORPHAN_COLUMNS, Math.max(ordered.length, 1));
      ordered.forEach((n, index) => {
        const size = nodeSize(n.kind);
        const col = index % columns;
        const row = Math.floor(index / columns);
        placements.set(n.id, {
          x: PAD + col * COLUMN_WIDTH,
          y: cursorY + PAD + row * ROW_GAP,
          w: size.w,
          h: size.h,
        });
      });
      cursorY += PAD * 2 + Math.ceil(ordered.length / columns) * ROW_GAP;
      continue;
    }

    const rows = new Map<number, TopologyNode[]>();
    for (const n of group.nodes) {
      const col = FLOW_KIND_ORDER.indexOf(n.kind);
      const list = rows.get(col);
      if (list) list.push(n);
      else rows.set(col, [n]);
    }
    // 以「宿主节点」所在列的行序对齐：同一 VM 的容器/服务/任务按序排布
    const primaryCol = [...rows.keys()].sort((a, b) => a - b)[0] ?? 0;
    const primary = rows.get(primaryCol) ?? [];
    const rowIndexById = new Map<string, number>();
    primary.forEach((n, i) => rowIndexById.set(n.id, i));

    const maxRows = Math.max(1, ...[...rows.values()].map((l) => l.length));
    for (const [col, list] of rows.entries()) {
      list.forEach((n, i) => {
        const size = nodeSize(n.kind);
        const row = col === primaryCol ? i : (rowIndexById.get(n.id) ?? i);
        const x = PAD + (col + 1) * COLUMN_WIDTH;
        const y = cursorY + PAD + row * ROW_GAP;
        placements.set(n.id, { x, y, w: size.w, h: size.h });
      });
    }
    cursorY += PAD * 2 + maxRows * ROW_GAP;
  }

  return {
    placements,
    nodesByCombo,
  };
}

function statusFill(status: NodeStatus): string {
  switch (status) {
    case 'healthy':
      return COLORS.healthySoft;
    case 'warning':
      return COLORS.warningSoft;
    case 'critical':
      return COLORS.criticalSoft;
    default:
      return COLORS.unknownSoft;
  }
}

/** 节点副标题：优先展示关键指标，回落到 API 提供的 subtitle。 */
function subtitleOf(node: TopologyNode): string {
  if (node.metrics?.length) {
    const m = node.metrics[0];
    const unit = m.unit === 'percent' ? '%' : m.unit === 'ratio' ? '' : ` ${m.unit}`;
    const value = m.unit === 'byte' ? `${(m.value / 1e6).toFixed(1)}MB` : m.value;
    return `${m.name} ${value}${unit}`;
  }
  return node.subtitle ?? '';
}

export const TopologyGraph = forwardRef<TopologyGraphHandle, TopologyGraphProps>(function TopologyGraph(
  {
    data,
    depth = 2,
    onDepthChange,
    selectedId,
    onSelect,
    compact = false,
    height = 560,
    emptyHint = '当前深度下没有可展示的资源。',
    className,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const fittedKeyRef = useRef('');
  const [kindFilter, setKindFilter] = useState<ResourceKind | 'all'>('all');
  const [ready, setReady] = useState(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const dataRef = useRef(data);
  dataRef.current = data;

  const comboParent = useMemo(() => {
    const map: Record<string, string | null> = {};
    for (const c of data.combos ?? []) map[c.id] = c.parent ?? null;
    return map;
  }, [data.combos]);

  const { graphData, placements, visibleNodes } = useMemo(() => {
    const allCombos = kindFilter !== 'all';
    const comboIds = new Set((data.combos ?? []).map((combo) => combo.id));
    const { placements: place } = computeLayout(data.nodes, depth, comboParent, { allCombos, kindFilter });
    let visible = data.nodes.filter((n) => place.has(n.id));
    if (kindFilter !== 'all') visible = visible.filter((n) => n.kind === kindFilter);

    const nodes = visible.map((n) => {
      const p = place.get(n.id) as Placement;
      const badgeCount = n.incident_count ?? 0;
      const isSelected = selectedId === n.id;
      const isDimmed = Boolean(selectedId) && !isSelected;
      const subtitle = subtitleOf(n);
      return {
        id: n.id,
        // Drop inferred parents that the server omitted; G6 rejects dangling combo references.
        combo:
          kindFilter === 'all' && FLOW_KIND_ORDER.includes(n.kind) && n.combo && comboIds.has(n.combo)
            ? n.combo
            : undefined,
        data: { raw: n, kind: n.kind, status: n.status },
        style: {
          x: p.x + p.w / 2,
          y: p.y + p.h / 2,
          size: [p.w, p.h] as [number, number],
          radius: 3,
          fill: statusFill(n.status),
          fillOpacity: isDimmed ? 0.45 : 1,
          stroke: STATUS_COLOR[n.status] ?? COLORS.unknown,
          lineWidth: isSelected ? 2.4 : 1.1,
          lineDash: n.status === 'unknown' ? [4, 3] : undefined,
          opacity: isDimmed ? 0.5 : 1,
          zIndex: isSelected ? 10 : 1,
          label: true,
          labelText: ` ${n.label}  `,
          labelPlacement: 'top' as const,
          labelFill: COLORS.ink,
          labelFontSize: 12,
          labelFontWeight: 500,
          labelFontFamily: SANS_FONT,
          labelBackground: false,
          labelOffsetY: -p.h / 2 + 6,
          badges: [
            ...(badgeCount > 0
              ? [
                  {
                    text: `● ${badgeCount}`,
                    placement: 'right-top' as const,
                    fontSize: 10,
                    fill: '#ffffff',
                    backgroundFill: COLORS.warning,
                    backgroundStroke: '#ffffff',
                    backgroundLineWidth: 1,
                    backgroundRadius: 7,
                    padding: [1, 4] as [number, number],
                  },
                ]
              : []),
            ...(subtitle
              ? [
                  {
                    text: subtitle,
                    placement: 'bottom' as const,
                    fontSize: 10,
                    fill: COLORS.inkTertiary,
                    fontFamily: MONO_FONT,
                  },
                ]
              : []),
          ],
        },
      };
    });

    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = data.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e: TopologyEdge) => {
        const touchesSelection = selectedId === e.source || selectedId === e.target;
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          data: { raw: e },
          style: {
            stroke: touchesSelection ? COLORS.primary : COLORS.ruleStrong,
            lineWidth: touchesSelection ? 1.8 : 1,
            opacity: selectedId && !touchesSelection ? 0.28 : 0.9,
            endArrow: true,
            endArrowType: 'triangle' as const,
            endArrowSize: 7,
            labelText: e.relation === 'contains' ? '' : (e.label ?? e.relation),
            labelFontSize: 9,
            labelFill: COLORS.inkTertiary,
            labelFontFamily: MONO_FONT,
            labelBackground: true,
            labelBackgroundFill: '#fcfdfe',
            labelBackgroundOpacity: 0.9,
            labelPadding: [0, 3] as [number, number],
          },
        };
      });

    const comboChildCount = new Map<string, number>();
    for (const n of visible) {
      const key =
        FLOW_KIND_ORDER.includes(n.kind) && n.combo && comboIds.has(n.combo) ? n.combo : '';
      comboChildCount.set(key, (comboChildCount.get(key) ?? 0) + 1);
    }

    // A host combo can contain only another combo, with no direct node members.
    // Keep every ancestor of a populated combo so G6 never receives a dangling parent.
    const activeComboIds = new Set(
      [...comboChildCount.entries()].filter(([id, count]) => id && count > 0).map(([id]) => id),
    );
    const comboById = new Map((data.combos ?? []).map((combo) => [combo.id, combo]));
    for (const id of [...activeComboIds]) {
      let parent = comboById.get(id)?.parent;
      while (parent && comboById.has(parent) && !activeComboIds.has(parent)) {
        activeComboIds.add(parent);
        parent = comboById.get(parent)?.parent;
      }
    }
    const combos = (data.combos ?? []).filter((c) => kindFilter === 'all' && activeComboIds.has(c.id)).map((c) => {
      const childCount = comboChildCount.get(c.id) ?? 0;
      const hasNestedCombo = (data.combos ?? []).some((child) => child.parent === c.id && activeComboIds.has(child.id));
      return {
        id: c.id,
        combo: c.parent && comboIds.has(c.parent) ? c.parent : undefined,
        data: { raw: c },
        style: {
          padding: c.kind === 'host' ? 18 : 14,
          radius: 4,
          fill: c.kind === 'host' ? '#f3f6f9' : '#f8fafb',
          fillOpacity: 0.72,
          stroke: c.kind === 'host' ? COLORS.ruleStrong : COLORS.rule,
          lineWidth: c.kind === 'host' ? 1.2 : 1,
          lineDash: c.kind === 'host' ? undefined : [5, 3],
          label: true,
          labelText: ` ${c.label} · ${KIND_TEXT[c.kind] ?? c.kind}${
            childCount > 0 ? ` · ${childCount} 个资源` : hasNestedCombo ? ' · 含嵌套资源' : ' · 空'
          } `,
          labelFill: c.kind === 'host' ? COLORS.inkSecondary : COLORS.inkTertiary,
          labelFontSize: 11,
          labelFontFamily: MONO_FONT,
          labelPlacement: 'top-left' as const,
          labelBackground: true,
          labelBackgroundFill: c.kind === 'host' ? '#e9eef3' : '#eef2f5',
          labelBackgroundRadius: 2,
          labelPadding: [1, 5] as [number, number],
          collapsed: false,
          zIndex: -1,
        },
      };
    });

    return {
      graphData: { nodes, edges, combos } as unknown as GraphData,
      placements: place,
      visibleNodes: visible,
    };
  }, [data, depth, comboParent, selectedId, kindFilter]);

  useEffect(() => {
    if (selectedId && !visibleNodes.some((node) => node.id === selectedId)) {
      onSelectRef.current?.(null);
    }
  }, [selectedId, visibleNodes]);

  const visibleIdsKey = useMemo(() => visibleNodes.map((n) => n.id).join('|'), [visibleNodes]);
  const fitKey = `${depth}|${kindFilter}|${visibleIdsKey}|${(data.combos ?? []).map((c) => c.id).join('|')}`;

  /** 初始化图实例（仅一次）。 */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const graph = new Graph({
      container,
      autoResize: true,
      animation: false,
      background: 'transparent',
      padding: 24,
      zoomRange: [0.2, 3],
      behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
      node: { type: 'rect', state: { selected: { lineWidth: 2.6 } } },
      edge: { type: 'line' },
      combo: { type: 'rect' },
    });
    graphRef.current = graph;

    // 事件里的 target 是 G6 元素实例，元素数据用 idOf 取出（G6 v5 官方口径）
    graph.on('node:click', (event) => {
      const target = (event as IElementEvent).target as unknown as {
        data?: Record<string, unknown>;
        id?: string;
      };
      const id = target?.data ? String(idOf(target.data as never)) : String(target?.id ?? '');
      if (!id) return;
      const node = dataRef.current.nodes.find((n) => n.id === id) ?? null;
      onSelectRef.current?.(node);
    });
    graph.on('canvas:click', () => onSelectRef.current?.(null));

    setReady(true);
    return () => {
      setReady(false);
      graphRef.current = null;
      graph.destroy();
    };
    // 仅初始化一次；数据通过 setData 更新
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 渲染 / 增量更新数据。 */
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !ready) return;
    let cancelled = false;
    void (async () => {
      graph.setData(graphData);
      await graph.render();
      if (cancelled) return;
      const total = visibleNodes.reduce((acc, n) => {
        const p = placements.get(n.id);
        return p ? Math.max(acc, p.x + p.w, p.y + p.h) : acc;
      }, 0);
      if (total > 0 && fittedKeyRef.current !== fitKey) {
        await graph.fitView({ when: 'always' });
        fittedKeyRef.current = fitKey;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [graphData, ready, visibleNodes, placements, fitKey]);

  const fit = useCallback(() => void graphRef.current?.fitView({ when: 'always' }), []);
  const zoomIn = useCallback(() => {
    const g = graphRef.current;
    if (!g) return;
    const z = g.getZoom();
    void g.zoomTo(Math.min(3, z * 1.2), { duration: 120 });
  }, []);
  const zoomOut = useCallback(() => {
    const g = graphRef.current;
    if (!g) return;
    const z = g.getZoom();
    void g.zoomTo(Math.max(0.2, z / 1.2), { duration: 120 });
  }, []);
  const focusOn = useCallback(
    (id: string) => {
      const g = graphRef.current;
      if (!g) return;
      const p = placements.get(id);
      if (!p) return;
      void g.focusElement(id, { duration: 200 }).catch(() => {
        void g.translateTo([-(p.x - 120), -(p.y - 120)], { duration: 200 });
      });
    },
    [placements],
  );

  useImperativeHandle(ref, () => ({ fit, zoomIn, zoomOut, focus: focusOn }), [fit, zoomIn, zoomOut, focusOn]);

  const kindOptions = useMemo(() => {
    const present = [...new Set(data.nodes.map((n) => n.kind))];
    const ordered = [
      ...KIND_ORDER.filter((kind) => present.includes(kind)),
      ...present.filter((kind) => !KIND_ORDER.includes(kind)).sort((a, b) => a.localeCompare(b)),
    ];
    return [
      { value: 'all', label: `全部资源 (${data.nodes.length})` },
      ...ordered.map((k) => ({
        value: k,
        label: `${KIND_TEXT[k] ?? k} (${data.nodes.filter((n) => n.kind === k).length})`,
      })),
    ];
  }, [data.nodes]);

  const isEmpty = visibleNodes.length === 0;

  return (
    <div className={`${styles.shell} ${className ?? ''}`} style={{ height }}>
      {!compact ? (
        <div className={styles.toolbar}>
          <span className="ts-eyebrow">拓扑层级</span>
          <Segmented
            size="small"
            value={depth}
            onChange={(v) => onDepthChange?.(Number(v) as TopologyDepth)}
            options={[
              { label: 'L1 云平台', value: 1 },
              { label: 'L2 工作负载', value: 2 },
              { label: 'L3 进程', value: 3 },
            ]}
          />
          <Select
            size="small"
            value={kindFilter}
            onChange={(v) => setKindFilter(v as ResourceKind | 'all')}
            options={kindOptions}
            style={{ width: 168 }}
          />
          <span className={styles.hint}>
            点击节点查看详情 · 拖拽平移 / 滚轮缩放 · {visibleNodes.length} 个可见资源
          </span>
        </div>
      ) : null}

      <div className={styles.canvasWrap}>
        <div className={styles.canvas} ref={containerRef} />
        <div className={styles.corner}>
          <Tooltip title="放大">
            <Button size="small" icon={<Icon name="plus" size={13} />} onClick={zoomIn} aria-label="放大" />
          </Tooltip>
          <Tooltip title="缩小">
            <Button size="small" icon={<Icon name="minus" size={13} />} onClick={zoomOut} aria-label="缩小" />
          </Tooltip>
          <Tooltip title="适应画布">
            <Button size="small" icon={<Icon name="fit" size={13} />} onClick={fit} aria-label="适应画布" />
          </Tooltip>
        </div>
        {isEmpty ? <div className={styles.overlay}>{emptyHint}</div> : null}
        {!ready ? <div className={styles.overlay}>正在初始化拓扑画布…</div> : null}
      </div>

      <div className={styles.legend}>
        <span className="ts-eyebrow">状态</span>
        <span className={styles.legendGroup}>
          {(['healthy', 'warning', 'critical', 'unknown'] as NodeStatus[]).map((s) => (
            <span key={s} className={styles.legendItem}>
              <i className={styles.swatch} style={{ background: statusFill(s), borderColor: STATUS_COLOR[s] }} />
              {STATUS_TEXT[s]}
            </span>
          ))}
        </span>
        <span className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <i className={styles.swatch} style={{ background: COLORS.surface, borderColor: COLORS.ruleStrong }} />
            资源种类
          </span>
          {KIND_ORDER.filter((k) => data.nodes.some((node) => node.kind === k)).map((k) => (
            <span key={k} className={styles.legendItem}>
              <i className={styles.swatchBar} style={{ background: COLORS.inkTertiary }} />
              {KIND_TEXT[k]}
            </span>
          ))}
        </span>
        <span className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <i className={`${styles.swatch}`} style={{ background: COLORS.warning, borderRadius: 7 }} />● 角标 =
            关联告警数
          </span>
        </span>
      </div>
    </div>
  );
});

export function subGraphToTopology(graph: SubGraph): Pick<TopologyResponse, 'nodes' | 'edges' | 'combos'> {
  const comboIds = new Set(graph.nodes.map((n) => n.combo).filter(Boolean) as string[]);
  return {
    nodes: graph.nodes,
    edges: graph.edges,
    combos: [...comboIds].map((id) => ({ id, label: id.replace('combo:', ''), kind: 'vm' as const, parent: null })),
  };
}
