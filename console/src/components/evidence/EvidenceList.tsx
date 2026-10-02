import { useMemo, useState } from 'react';
import { Button, Segmented, Select, Tooltip } from 'antd';
import styles from './EvidenceList.module.css';
import { Icon } from '@/components/common/Icon';
import { EvidenceKindTag, LayerTag, SeverityTag } from '@/components/common/Tags';
import { fmtClockMs, fmtValue } from '@/utils/format';
import type { EvidenceItem, EvidenceLayer, Severity } from '@/types';
import { SEVERITY_TEXT } from '@/theme/tokens';

const SEVERITY_RANK: Record<Severity, number> = { critical: 0, major: 1, warning: 2, info: 3 };

interface EvidenceListProps {
  items: EvidenceItem[];
  /** 高亮的证据 ID（诊断页由 score_breakdown 的 evidence_ids 传入） */
  highlightIds?: string[];
  /** 紧凑模式：详情抽屉内使用 */
  dense?: boolean;
  emptyText?: string;
}

/**
 * 证据列表：每条证据展示 evidence_id / signal / 来源类别 / 层级 / 资源 / 时间 / 描述，
 * 展开后可查看原始 payload（运维排查与评审核对的依据）。
 */
export function EvidenceList({ items, highlightIds = [], dense = false, emptyText }: EvidenceListProps) {
  const [openIds, setOpenIds] = useState<string[]>([]);
  const [layer, setLayer] = useState<EvidenceLayer | 'all'>('all');
  const [severity, setSeverity] = useState<Severity | 'all'>('all');
  const [sortBySeverity, setSortBySeverity] = useState(false);

  const highlighted = useMemo(() => new Set(highlightIds), [highlightIds]);

  const filtered = useMemo(() => {
    const list = items.filter(
      (e) => (layer === 'all' || e.layer === layer) && (severity === 'all' || e.severity === severity),
    );
    if (sortBySeverity) {
      return [...list].sort(
        (a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || a.observed_at.localeCompare(b.observed_at),
      );
    }
    return list;
  }, [items, layer, severity, sortBySeverity]);

  const layerOptions = useMemo(() => {
    const set = new Set(items.map((e) => e.layer));
    return [
      { value: 'all', label: `全部层级 (${items.length})` },
      ...[...set].map((l) => ({ value: l, label: `${l} (${items.filter((e) => e.layer === l).length})` })),
    ];
  }, [items]);

  const toggle = (id: string) =>
    setOpenIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  if (items.length === 0) {
    return (
      <div className={styles.empty}>
        {emptyText ??
          '该关联簇没有可展示的证据。可能原因：证据来源被禁用（platform / prometheus 不可用），或窗口内确实无异常信号。'}
      </div>
    );
  }

  return (
    <div>
      <div className={styles.toolbar}>
        <span className="ts-eyebrow">证据清单</span>
        <span className="ts-inline-meta">
          {filtered.length}/{items.length} 条
        </span>
        <Select
          size="small"
          value={layer}
          onChange={(v) => setLayer(v as EvidenceLayer | 'all')}
          options={layerOptions}
          style={{ width: 168 }}
        />
        <Segmented
          size="small"
          value={severity}
          onChange={(v) => setSeverity(v as Severity | 'all')}
          options={[
            { label: '全部', value: 'all' },
            { label: '严重', value: 'critical' },
            { label: '重要', value: 'major' },
            { label: '警告', value: 'warning' },
            { label: '提示', value: 'info' },
          ]}
        />
        <Button
          size="small"
          type={sortBySeverity ? 'primary' : 'default'}
          onClick={() => setSortBySeverity((v) => !v)}
        >
          按严重度排序
        </Button>
        <Button
          size="small"
          onClick={() => setOpenIds(openIds.length === filtered.length ? [] : filtered.map((e) => e.evidence_id))}
        >
          {openIds.length === filtered.length ? '收起全部' : '展开全部'}
        </Button>
      </div>

      <div className={styles.list}>
        {filtered.map((item) => {
          const open = openIds.includes(item.evidence_id);
          const isKey = highlighted.has(item.evidence_id);
          return (
            <div className={styles.item} key={item.evidence_id}>
              <div
                className={`${styles.itemHead} ${styles[`sevbar_${item.severity}`]} ${open ? styles.itemOpen : ''}`}
                role="button"
                tabIndex={0}
                aria-expanded={open}
                onClick={() => toggle(item.evidence_id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggle(item.evidence_id);
                  }
                }}
              >
                <div className={styles.idCell}>
                  {isKey ? '★ ' : ''}
                  {item.evidence_id}
                </div>
                <div className={styles.main}>
                  <div className={styles.signal}>{item.signal}</div>
                  {!dense ? <div className={styles.desc}>{item.description}</div> : null}
                  <div className={styles.meta}>
                    <span className={styles.metaItem}>
                      <Icon name="box" size={11} />
                      {item.resource_id}
                    </span>
                    {item.resource_name && item.resource_name !== item.resource_id ? (
                      <span className={styles.metaItem}>({item.resource_name})</span>
                    ) : null}
                    <span className={styles.metaItem}>
                      <Icon name="clock" size={11} />
                      {fmtClockMs(item.observed_at)}
                    </span>
                    {item.correlation_id ? (
                      <span className={styles.metaItem}>corr {item.correlation_id}</span>
                    ) : null}
                    {item.task_id ? <span className={styles.metaItem}>{item.task_id}</span> : null}
                    {item.origin ? <span className={styles.metaItem}>origin {item.origin}</span> : null}
                  </div>
                </div>
                <div className={styles.right}>
                  <SeverityTag severity={item.severity} tiny />
                  <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                    <EvidenceKindTag kind={item.kind} tiny />
                    <LayerTag layer={item.layer} tiny />
                  </span>
                  {item.value !== undefined ? (
                    <span className={styles.value}>
                      {fmtValue(item.value, item.unit)}
                      {item.baseline !== undefined ? (
                        <span className={styles.sourceList}> (基线 {fmtValue(item.baseline, item.unit)})</span>
                      ) : null}
                    </span>
                  ) : null}
                  <span className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`}>
                    <Icon name="chevron" size={12} />
                  </span>
                </div>
              </div>

              {open ? (
                <div className={styles.payload}>
                  <div className={styles.payloadGrid}>
                    <span className={styles.payloadKey}>evidence_id</span>
                    <span>{item.evidence_id}</span>
                    <span className={styles.payloadKey}>observed_at</span>
                    <span>{item.observed_at}</span>
                    <span className={styles.payloadKey}>layer / kind</span>
                    <span>
                      {item.layer} / {item.kind}
                    </span>
                    <span className={styles.payloadKey}>resource</span>
                    <span>
                      {item.resource_id}
                      {item.resource_name ? ` (${item.resource_name})` : ''}
                    </span>
                    {item.correlation_id ? (
                      <>
                        <span className={styles.payloadKey}>correlation_id</span>
                        <span>{item.correlation_id}</span>
                      </>
                    ) : null}
                    {item.task_id ? (
                      <>
                        <span className={styles.payloadKey}>task_id</span>
                        <span>{item.task_id}</span>
                      </>
                    ) : null}
                    {item.source_event_ids?.length ? (
                      <>
                        <span className={styles.payloadKey}>source_event_ids</span>
                        <span className={styles.sourceList}>{item.source_event_ids.join(', ')}</span>
                      </>
                    ) : null}
                    <span className={styles.payloadKey}>mode</span>
                    <span>{item.mode ?? 'real'}</span>
                  </div>
                  <div className={styles.payloadHead} style={{ marginTop: 10 }}>
                    <span className="ts-eyebrow">原始 payload</span>
                    <Tooltip title="复制为 JSON">
                      <Button
                        size="small"
                        type="text"
                        onClick={(e) => {
                          e.stopPropagation();
                          void navigator.clipboard?.writeText(JSON.stringify(item.payload ?? {}, null, 2));
                        }}
                      >
                        复制
                      </Button>
                    </Tooltip>
                  </div>
                  <pre className={styles.json}>{JSON.stringify(item.payload ?? { note: '无 payload' }, null, 2)}</pre>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className={styles.toolbar} style={{ borderTop: '1px solid var(--ts-rule)', borderBottom: 'none' }}>
        <span className={styles.sourceList}>
          严重度图例：{Object.entries(SEVERITY_TEXT).map(([k, v]) => `${v}(${k})`).join(' · ')}
        </span>
      </div>
    </div>
  );
}
