import { useMemo, useState } from 'react';
import styles from './LayerTimeline.module.css';
import { Icon } from '@/components/common/Icon';
import { LayerTag, PlainTag, SeverityTag } from '@/components/common/Tags';
import { LAYER_COLOR, LAYER_TEXT } from '@/theme/tokens';
import { fmtClockMs } from '@/utils/format';
import { normalizeEvidenceLayer } from '@/utils/evidenceLayer';
import type { EvidenceLayer, TimelineEntry } from '@/types';

interface LayerTimelineProps {
  entries: TimelineEntry[];
  /** 高亮指定 incident（详情页） */
  incidentId?: string;
  emptyText?: string;
  /** 是否显示层级过滤条 */
  filterable?: boolean;
}

interface Group {
  key: string;
  /** 同一秒内的事件合并为一行，便于横向对比各层同时刻状态 */
  time: string;
  items: TimelineEntry[];
}

function groupByTime(entries: TimelineEntry[]): Group[] {
  const map = new Map<string, Group>();
  for (const e of entries) {
    const key = e.observed_at.slice(0, 19);
    const group = map.get(key);
    if (group) group.items.push(e);
    else map.set(key, { key, time: e.observed_at, items: [e] });
  }
  return [...map.values()].sort((a, b) => a.key.localeCompare(b.key));
}

/**
 * 分层事件时间线。
 *
 * 结构即信息：左列时间、次列层级、中间刻度尺、右侧事件体。
 * 层级色顺序固定为 云平台 → 虚拟机 → 容器 → 应用，读者能直接看到
 * 「系统层信号在前、应用层表现在后」的因果次序。
 */
export function LayerTimeline({
  entries,
  incidentId,
  emptyText = '窗口内没有事件。',
  filterable = true,
}: LayerTimelineProps) {
  const [activeLayers, setActiveLayers] = useState<EvidenceLayer[] | null>(null);
  const normalizedEntries = useMemo(
    () => entries.map((entry) => ({ ...entry, layer: normalizeEvidenceLayer(entry.layer, entry.resource_id) })),
    [entries],
  );

  const groups = useMemo(() => {
    const filtered = activeLayers
      ? normalizedEntries.filter((e) => activeLayers.includes(e.layer))
      : normalizedEntries;
    return groupByTime(filtered);
  }, [normalizedEntries, activeLayers]);

  const layerCounts = useMemo(() => {
    const counts = new Map<EvidenceLayer, number>();
    for (const e of normalizedEntries) counts.set(e.layer, (counts.get(e.layer) ?? 0) + 1);
    return counts;
  }, [normalizedEntries]);

  const toggleLayer = (layer: EvidenceLayer) => {
    setActiveLayers((prev) => {
      const base = prev ?? [...layerCounts.keys()];
      const next = base.includes(layer) ? base.filter((l) => l !== layer) : [...base, layer];
      return next.length === layerCounts.size ? null : next;
    });
  };

  const total = groups.reduce((acc, g) => acc + g.items.length, 0);

  return (
    <div className={styles.wrap}>
      {filterable ? (
        <div className={styles.toolbar}>
          <span className="ts-eyebrow">分层时间线</span>
          <span className="ts-inline-meta">
            {total} 条事件 · {groups.length} 个时刻
          </span>
          <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
            {[...layerCounts.entries()].map(([layer, count]) => {
              const off = activeLayers !== null && !activeLayers.includes(layer);
              return (
                <button
                  key={layer}
                  type="button"
                  onClick={() => toggleLayer(layer)}
                  style={{
                    all: 'unset',
                    cursor: 'pointer',
                    opacity: off ? 0.42 : 1,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    fontFamily: 'var(--ts-mono)',
                    fontSize: 11,
                    border: '1px solid var(--ts-rule)',
                    borderRadius: 2,
                    padding: '1px 6px',
                    background: off ? 'transparent' : '#fff',
                  }}
                  title={`${off ? '显示' : '隐藏'} ${LAYER_TEXT[layer]}`}
                >
                  <i className={styles.chip} style={{ background: LAYER_COLOR[layer] }} />
                  {LAYER_TEXT[layer]} {count}
                </button>
              );
            })}
          </span>
        </div>
      ) : null}

      {groups.length === 0 ? (
        <div className={styles.empty}>{emptyText}</div>
      ) : (
        <div className={styles.stream}>
          {groups.map((group) => (
            <div className={styles.group} key={group.key}>
              <div className={styles.timeCell}>{fmtClockMs(group.time).slice(0, 8)}</div>
              <div className={styles.layerCell}>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
                  {[...new Set(group.items.map((i) => i.layer))].map((l) => (
                    <span
                      key={l}
                      style={{
                        fontFamily: 'var(--ts-mono)',
                        fontSize: 10,
                        color: LAYER_COLOR[l],
                        borderRight: `2px solid ${LAYER_COLOR[l]}`,
                        paddingRight: 5,
                      }}
                    >
                      {LAYER_TEXT[l].replace('层', '')}
                    </span>
                  ))}
                </span>
              </div>
              <div className={styles.rail}>
                <span className={styles.tickDot} style={{ borderColor: LAYER_COLOR[group.items[0].layer] }} />
                {group.items.slice(1).map((item, i) => (
                  <span
                    className={styles.tick}
                    key={`${item.evidence_id ?? item.signal}-${i}`}
                    style={{ top: 30 + i * 34, background: LAYER_COLOR[item.layer] }}
                  />
                ))}
              </div>
              <div className={styles.rows}>
                {group.items.map((item) => (
                  <div className={styles.row} key={`${item.signal}-${item.resource_id}-${item.evidence_id ?? ''}`}>
                    <div className={styles.rowHead}>
                      <span className={styles.signal}>{item.signal}</span>
                      <SeverityTag severity={item.severity} tiny />
                      <LayerTag layer={item.layer} tiny />
                      {incidentId && item.incident_id && item.incident_id !== incidentId ? (
                        <PlainTag tiny color="var(--ts-ink-3)" dashed>
                          归属 {item.incident_id}
                        </PlainTag>
                      ) : null}
                    </div>
                    <div className={styles.desc}>{item.description}</div>
                    <div className={styles.meta}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <Icon name="box" size={10} />
                        {item.resource_name || item.resource_id}
                      </span>
                      {item.evidence_id ? <span>evidence {item.evidence_id}</span> : null}
                      <span>{fmtClockMs(item.observed_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className={styles.legend}>
        <span className="ts-eyebrow">层级图例</span>
        {(['application', 'container', 'vm', 'zsvirt'] as EvidenceLayer[]).map((layer) => (
          <span className={styles.legendItem} key={layer}>
            <i className={styles.chip} style={{ background: LAYER_COLOR[layer] }} />
            {LAYER_TEXT[layer]}
          </span>
        ))}
        <span style={{ color: 'var(--ts-ink-3)' }}>
          同一时刻的多个层级事件合并显示：系统层信号先于应用层表现
        </span>
      </div>
    </div>
  );
}
