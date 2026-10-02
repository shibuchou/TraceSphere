import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Alert, AutoComplete, Button, Input, Segmented, Select, Tooltip } from 'antd';
import styles from './pages.module.css';
import { FoldPanel, Panel, VStack } from '@/components/common/Panel';
import { Icon } from '@/components/common/Icon';
import { MetricCard, PageHead } from '@/components/common/PageHead';
import { InlineLoading, LoadingPanel } from '@/components/common/States';
import { ApiErrorState } from '@/components/common/ApiErrorState';
import { PlainTag, SeverityTag } from '@/components/common/Tags';
import { SourceStatusStrip } from '@/components/common/DataSourceBadge';
import { EvidenceList } from '@/components/evidence/EvidenceList';
import { CandidateList, DimensionBars, MatchScoreHeader } from '@/components/diagnosis/ScoreBreakdown';
import { LayerTimeline } from '@/components/timeline/LayerTimeline';
import { SuggestionList } from './IncidentDetailPage';
import { useRuleLibrary } from '@/components/rules/RuleLibrary';
import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { useApp } from '@/state/AppContext';
import { SCENARIOS, scenarioSamples } from '@/data/scenarios';
import { COLORS } from '@/theme/tokens';
import { fmtDateTime } from '@/utils/format';
import type { Diagnosis } from '@/types';

const WINDOWS = [
  { label: '15 分钟', seconds: 900 },
  { label: '1 小时', seconds: 3600 },
  { label: '6 小时', seconds: 21600 },
];

type FocusKind = 'correlation_id' | 'resource_id';

export function DiagnosisPage() {
  const app = useApp();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialCorrelation = searchParams.get('correlation_id') ?? '';
  const initialResource = searchParams.get('resource_id') ?? '';

  const [focusKind, setFocusKind] = useState<FocusKind>(
    initialResource && !initialCorrelation ? 'resource_id' : 'correlation_id',
  );
  const [input, setInput] = useState(initialCorrelation || initialResource || app.scenario.correlation_id);
  const [inputError, setInputError] = useState<string | null>(null);
  const [windowSeconds, setWindowSeconds] = useState(900);
  const [topN, setTopN] = useState(3);
  const [submitted, setSubmitted] = useState<{ kind: FocusKind; value: string } | null>(
    (initialCorrelation || initialResource || app.scenario.correlation_id)
      ? {
          kind: initialResource && !initialCorrelation ? 'resource_id' : 'correlation_id',
          value: initialCorrelation || initialResource || app.scenario.correlation_id,
        }
      : null,
  );

  const result = useAsync(
    (signal) => {
      if (!submitted) return Promise.reject(new Error('尚未提交诊断请求'));
      const payload =
        submitted.kind === 'correlation_id'
          ? { correlation_id: submitted.value, window_seconds: windowSeconds, top_n: topN }
          : { resource_id: submitted.value, window_seconds: windowSeconds, top_n: topN };
      return api.diagnose(payload, { signal });
    },
    [submitted?.kind, submitted?.value, windowSeconds, topN, app.refreshToken],
    { enabled: Boolean(submitted) },
  );

  /** 场景切换（顶栏演示路径）时跟随更新输入。 */
  useEffect(() => {
    const fromQuery = searchParams.get('correlation_id');
    if (fromQuery && fromQuery !== input) {
      setFocusKind('correlation_id');
      setInput(fromQuery);
      setSubmitted({ kind: 'correlation_id', value: fromQuery });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const samples = useMemo(() => scenarioSamples(), []);
  const ruleLibrary = useRuleLibrary();

  const submit = (kind: FocusKind, value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      setInputError(kind === 'resource_id' ? '请输入资源标识。' : '请输入关联锚点。');
      return;
    }
    if (kind === 'resource_id' && !/^[a-z][a-z0-9_-]*:.+$/i.test(trimmed)) {
      setInputError('资源标识应包含类型前缀，例如 container:资源ID。');
      return;
    }
    setInputError(null);
    setFocusKind(kind);
    setInput(trimmed);
    setSubmitted({ kind, value: trimmed });
    const params = new URLSearchParams(searchParams);
    params.delete('correlation_id');
    params.delete('resource_id');
    params.set(kind, trimmed);
    params.set('scenario', app.scenarioId);
    setSearchParams(params, { replace: true });
  };

  const diagnoses = result.data?.diagnoses ?? [];
  const evidence = result.data?.evidence ?? [];
  const impactScope = result.data?.impact?.scope ?? [];
  const timeline = result.data?.timeline ?? [];
  const [activeRule, setActiveRule] = useState<string | undefined>(undefined);
  const active: Diagnosis | undefined =
    diagnoses.find((d) => d.rule === activeRule) ?? diagnoses[0];

  useEffect(() => {
    setActiveRule(diagnoses[0]?.rule);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.data]);

  return (
    <div className={styles.page}>
      <PageHead
        title="根因诊断"
        sub="POST /api/v1/diagnose"
        desc="输入 correlation_id（一次 Agent 任务的应用层锚点）或 resource_id（系统层资源），在指定时间窗内执行规则匹配，输出按 Evidence Match 降序的根因候选 Top-N。"
      />

      <Panel
        title="诊断请求"
        icon="search"
        subtitle="API.md §4.5"
        bodyPadding="default"
        extra={
          result.loading && result.data ? <InlineLoading label="重新诊断中" /> : null
        }
      >
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className="ts-eyebrow">查询维度</span>
            <Segmented
              value={focusKind}
              onChange={(v) => {
                const nextKind = v as FocusKind;
                if (nextKind === focusKind) return;
                setFocusKind(nextKind);
                setSubmitted(null);
                setInputError(null);
                setInput(scenarioSamples().find((sample) => sample.kind === nextKind)?.value ?? '');
                const params = new URLSearchParams(searchParams);
                params.delete('correlation_id');
                params.delete('resource_id');
                setSearchParams(params, { replace: true });
              }}
              options={[
                { label: 'correlation_id', value: 'correlation_id' },
                { label: 'resource_id', value: 'resource_id' },
              ]}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '1 1 340px', minWidth: 280 }}>
            <span className="ts-eyebrow">
              {focusKind === 'correlation_id' ? '关联锚点（一次 Agent 任务）' : '资源标识（资源前缀 + ID）'}
            </span>
            <AutoComplete
              value={input}
              onChange={(value) => {
                setInput(value);
                setInputError(null);
              }}
              onSelect={(value) => {
                const sample = samples.find((s) => s.value === value);
                submit(sample?.kind ?? focusKind, value);
              }}
              options={samples.map((s) => ({
                value: s.value,
                label: (
                  <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <PlainTag tiny color="var(--ts-ink-3)">
                      {s.kind}
                    </PlainTag>
                    <span className="ts-mono" style={{ fontSize: 12 }}>
                      {s.value}
                    </span>
                    <span style={{ color: 'var(--ts-ink-3)', fontSize: 11, marginLeft: 'auto' }}>
                      {s.label}
                    </span>
                  </span>
                ),
              }))}
              style={{ width: '100%' }}
            >
              <Input
                size="middle"
                placeholder="例如 d38fc66c8364 或 container:7196bcad3bc1"
                onPressEnter={() => submit(focusKind, input)}
                status={inputError ? 'error' : undefined}
                prefix={<Icon name="search" size={13} style={{ color: 'var(--ts-ink-3)' }} />}
                allowClear
              />
            </AutoComplete>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className="ts-eyebrow">时间窗</span>
            <Segmented
              value={windowSeconds}
              onChange={(v) => setWindowSeconds(Number(v))}
              options={WINDOWS.map((w) => ({ label: w.label, value: w.seconds }))}
            />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className="ts-eyebrow">Top-N</span>
            <Select
              size="middle"
              style={{ width: 92 }}
              value={topN}
              onChange={setTopN}
              options={[1, 2, 3, 4, 5].map((n) => ({ label: `${n} 条`, value: n }))}
            />
          </div>
          <Button
            type="primary"
            icon={<Icon name="diagnose" size={14} />}
            onClick={() => submit(focusKind, input)}
            loading={result.loading}
          >
            执行诊断
          </Button>
        </div>

        {inputError ? (
          <Alert type="error" showIcon message={inputError} style={{ marginTop: 10 }} />
        ) : null}

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12, alignItems: 'center' }}>
          <span className="ts-eyebrow">示例输入</span>
          {SCENARIOS.map((s) => (
            <Tooltip key={s.id} title={s.hint}>
              <Button size="small" onClick={() => submit('correlation_id', s.correlation_id)}>
                <span className="ts-mono" style={{ fontSize: 11 }}>
                  {s.correlation_id}
                </span>
                <span style={{ color: 'var(--ts-ink-3)', marginLeft: 6 }}>{s.label}</span>
              </Button>
            </Tooltip>
          ))}
          <span style={{ marginLeft: 'auto' }}>
            <SourceStatusStrip
              source={
                result.data
                  ? {
                      platform: result.data.sources.platform,
                      prometheus: result.data.sources.prometheus,
                      fixture: app.dataSource === 'fixture' ? 'mock' : undefined,
                    }
                  : undefined
              }
            />
          </span>
        </div>
      </Panel>

      {!submitted ? (
        <Panel title="等待输入" icon="info" bodyPadding="default">
          <div className={styles.empty}>
            输入 correlation_id 或 resource_id 后执行诊断。若不确定可用值，点击上方「示例输入」中的任一
            correlation_id。顶部演示路径和下方样例都可以快速填入查询条件。
          </div>
        </Panel>
      ) : result.error && !result.data ? (
        <ApiErrorState error={result.error} onRetry={result.reload} />
      ) : !result.data ? (
        <LoadingPanel rows={6} label="执行规则匹配" />
      ) : (
        <>
          <div className={styles.summaryRow}>
            <MetricCard
              label="候选根因"
              value={diagnoses.length}
              accent={COLORS.primary}
              foot={`Top-${topN} 按评分降序`}
            />
            <MetricCard
              label="参与评分证据"
              value={result.data.sources.evidence_count ?? evidence.length}
              accent={COLORS.primary}
              foot={`窗口内共 ${evidence.length} 条`}
            />
            <MetricCard
              label="Top-1 评分"
              value={active ? Math.round(active.match_score) : '—'}
              accent={COLORS.critical}
              foot={active ? active.rule : '—'}
            />
            <MetricCard
              label="时间窗"
              value={`${Math.round(windowSeconds / 60)}m`}
              accent={COLORS.warning}
              foot={`${fmtDateTime(result.data.window.from)} → ${fmtDateTime(result.data.window.to)}`}
            />
            <MetricCard
              label="影响任务"
              value={result.data.impact.counts.tasks ?? 0}
              accent={COLORS.warning}
              foot={`容器 ${result.data.impact.counts.containers ?? 0} · 服务 ${result.data.impact.counts.services ?? 0}`}
            />
          </div>

          {diagnoses.length === 0 ? (
            <Panel title="诊断结果" icon="diagnose" bodyPadding="default">
              <Alert
                type="warning"
                showIcon
                message="该时间窗内没有命中任何规则"
                description={
                  <span style={{ fontSize: 12 }}>
                    可能原因：1) 窗口内确实没有异常信号；2) 证据来源被禁用（platform / prometheus 不可用），
                    导致规则条款无法参与匹配；3) 查询的 correlation_id / resource_id 不在该窗口内。
                    可放宽时间窗或改用示例输入中的已知锚点重试。
                  </span>
                }
              />
            </Panel>
          ) : (
            <>
              <div className={styles.twoCol}>
                <VStack>
                  <Panel
                    title={`根因候选 Top-${diagnoses.length}`}
                    icon="diagnose"
                    subtitle={
                      active
                        ? `${active.rule}@v${active.rule_version} · ${active.diagnosis_id}`
                        : undefined
                    }
                    extra={
                      <Tooltip title="Evidence Match 为规则证据命中评分（0–100），非概率">
                        <span className="ts-inline-meta">评分语义</span>
                      </Tooltip>
                    }
                  >
                    {active ? (
                      <>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                          <SeverityTag severity={active.severity} />
                          <PlainTag color="var(--ts-ink-secondary)">{active.root_cause}</PlainTag>
                          {result.data.focus.correlation_id ? (
                            <PlainTag color="var(--ts-ink-3)" dashed>
                              corr {result.data.focus.correlation_id}
                            </PlainTag>
                          ) : null}
                        </div>
                        <MatchScoreHeader diagnosis={active} />
                        <div style={{ marginTop: 14 }}>
                          <div className="ts-eyebrow" style={{ marginBottom: 7 }}>
                            五维度明细（score / max · 依据）
                          </div>
                      <DimensionBars items={active.score_breakdown ?? []} />
                        </div>
                      </>
                    ) : null}
                  </Panel>

                  <Panel
                    title="处置建议"
                    icon="rule"
                    subtitle={active ? `规则 ${active.rule} 的 result.suggestions` : undefined}
                    bodyPadding="flush"
                  >
                    {active ? (
                      <SuggestionList suggestions={active.suggestions ?? []} fallback={active.rule} />
                    ) : (
                      <div className={styles.empty}>未选择候选。</div>
                    )}
                  </Panel>

                  <Panel
                    title="引用证据"
                    icon="evidence"
                    subtitle={`${active?.evidence_ids?.length ?? 0} 条 evidence_ids（★ 为当前候选命中）`}
                    bodyPadding="flush"
                  >
                    <EvidenceList
                      items={evidence}
                      highlightIds={active?.evidence_ids ?? []}
                      emptyText="该候选没有可展示的证据明细（evidence 字段为空或证据来源不可用）。"
                    />
                  </Panel>
                </VStack>

                <VStack>
                  <Panel
                    title="候选排序"
                    icon="layers"
                    subtitle="点击切换查看某条候选的完整明细"
                    bodyPadding="tight"
                  >
                    <div style={{ marginTop: 6 }}>
                      <CandidateList
                        candidates={diagnoses}
                        currentRule={active?.rule}
                        onSelect={(rule) => setActiveRule(rule)}
                      />
                    </div>
                  </Panel>

                  <Panel
                    title="影响范围"
                    icon="alert"
                    subtitle={`任务 ${result.data.impact.counts.tasks ?? 0} 个`}
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
                              <span style={{ display: 'flex', gap: 7, alignItems: 'center' }}>
                                <span style={{ fontWeight: 600, fontSize: 12 }}>{item.name}</span>
                                <PlainTag tiny color="var(--ts-ink-3)">
                                  {item.relation}
                                </PlainTag>
                              </span>
                              <span className="ts-inline-meta">{item.resource_id}</span>
                            </span>
                            <Link to={`/incidents?resource_id=${encodeURIComponent(item.resource_id)}`}>
                              <Button size="small" type="link">
                                告警
                              </Button>
                            </Link>
                          </div>
                        ))
                      )}
                    </div>
                  </Panel>

                  <Panel title="分层时间线" icon="clock" bodyPadding="flush">
                    <LayerTimeline
                      entries={timeline}
                      emptyText="该诊断窗口内没有事件明细。"
                    />
                  </Panel>
                </VStack>
              </div>

              <RuleLibraryPanel
                rules={ruleLibrary.data?.rules ?? []}
                loading={ruleLibrary.loading && !ruleLibrary.data}
                error={ruleLibrary.error?.message}
                onReload={ruleLibrary.reload}
                activeRule={active?.rule}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

/**
 * 规则库：展示三条规则的 YAML 关键结构 + 权重分布。
 * 目的：证明诊断是**配置驱动**（新增规则 = 新增 YAML），不是写死的 if/else。
 */
function RuleLibraryPanel({
  rules,
  loading,
  error,
  onReload,
  activeRule,
}: {
  rules: import('@/types').RuleDefinition[];
  loading: boolean;
  error?: string;
  onReload: () => void;
  activeRule?: string;
}) {
  const [openRule, setOpenRule] = useState<string | undefined>(activeRule);

  useEffect(() => {
    if (activeRule) setOpenRule(activeRule);
  }, [activeRule]);

  return (
    <Panel
      title="规则库"
      icon="rule"
      subtitle={`GET /api/v1/rules · ${rules.length} 条 YAML 规则（rule / evidence / correlation / result 四段结构）`}
      bodyPadding="default"
      extra={
        <Button size="small" icon={<Icon name="refresh" size={13} />} onClick={onReload}>
          重新读取
        </Button>
      }
    >
      {loading ? (
        <LoadingPanel rows={3} label="加载规则库" />
      ) : error ? (
        <div className={styles.empty}>{error}</div>
      ) : rules.length === 0 ? (
        <div className={styles.empty}>规则库为空：请确认 rca/rules/*.yaml 已部署。</div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {rules.map((r) => {
              const active = r.rule === openRule;
              return (
                <button
                  key={r.rule}
                  type="button"
                  onClick={() => setOpenRule(active ? undefined : r.rule)}
                  style={{
                    all: 'unset',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '4px 10px',
                    border: `1px solid ${active ? COLORS.primary : 'var(--ts-rule-strong)'}`,
                    background: active ? COLORS.primarySoft : '#fff',
                    borderRadius: 2,
                    fontFamily: 'var(--ts-mono)',
                    fontSize: 11.5,
                  }}
                >
                  <SeverityTag severity={r.severity} tiny showText={false} />
                  {r.rule}
                  <span style={{ color: 'var(--ts-ink-3)' }}>
                    v{r.version} · {r.evidence.length} 条款
                  </span>
                </button>
              );
            })}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {rules
              .filter((r) => !openRule || r.rule === openRule)
              .map((r) => (
                <RuleCard key={r.rule} rule={r} />
              ))}
          </div>

          <div className="ts-inline-meta" style={{ marginTop: 12 }}>
            新增检测规则 = 在 rca/rules/ 增加一个 YAML 文件并重启服务，引擎代码无需改动（方案 §6.3
            的可扩展性主张）。权重为相对值，引擎会按 Σ 归一化到 rule_match 维度的 55 分上限。
          </div>
        </>
      )}
    </Panel>
  );
}

function RuleCard({ rule }: { rule: import('@/types').RuleDefinition }) {
  const totalWeight = rule.evidence.reduce((acc, c) => acc + (c.weight ?? 0), 0);
  const requiredWeight = rule.evidence
    .filter((c) => !c.optional)
    .reduce((acc, c) => acc + (c.weight ?? 0), 0);

  const yaml = useMemo(() => {
    const lines: string[] = [];
    lines.push(`rule: ${rule.rule}`);
    lines.push(`version: ${rule.version}`);
    lines.push(`title: ${rule.title}`);
    lines.push(`severity: ${rule.severity}`);
    lines.push('evidence:');
    for (const c of rule.evidence) {
      const key = c.signal ? `signal: ${c.signal}` : c.metric ? `metric: ${c.metric}` : `signal_any: [${(c.signal_any ?? []).join(', ')}]`;
      lines.push(`  - ${key}`);
      if (c.kind) lines.push(`    kind: ${c.kind}`);
      if (c.kind_any?.length) lines.push(`    kind_any: [${c.kind_any.join(', ')}]`);
      if (c.layer) lines.push(`    layer: ${c.layer}`);
      lines.push(`    weight: ${c.weight}`);
      if (c.op) lines.push(`    op: "${c.op}"`);
      if (c.value !== undefined) lines.push(`    value: ${c.value}`);
      if (c.require_increase) lines.push('    require_increase: true');
      if (c.require_attribute) lines.push(`    require_attribute: ${c.require_attribute}`);
      if (c.status) lines.push(`    status: ${c.status}`);
      if (c.optional) lines.push('    optional: true');
      if (c.after) lines.push(`    after: ${c.after}`);
      if (c.match_any?.length) lines.push(`    match_any: [${c.match_any.join(', ')}]`);
    }
    lines.push('correlation:');
    for (const [k, v] of Object.entries(rule.correlation)) {
      lines.push(`  ${k}: ${Array.isArray(v) ? `[${v.join(', ')}]` : String(v)}`);
    }
    lines.push('result:');
    lines.push(`  root_cause: ${rule.result.root_cause}`);
    lines.push(`  label: ${rule.result.label}`);
    lines.push('  suggestions:');
    for (const s of rule.result.suggestions) {
      lines.push(`    - action: ${s.action}`);
      lines.push(`      title: ${s.title}`);
    }
    return lines.join('\n');
  }, [rule]);

  return (
    <div className={styles.ruleCard}>
      <div className={styles.ruleHead}>
        <SeverityTag severity={rule.severity} />
        <span className={styles.ruleTitle}>{rule.title}</span>
        <span className={styles.ruleMeta}>
          {rule.rule}@v{rule.version}
          {rule.path ? ` · ${rule.path}` : ''}
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <PlainTag tiny color="var(--ts-ink-3)">
            参与权重 Σ {requiredWeight} / 全量 Σ {totalWeight}
          </PlainTag>
          <PlainTag tiny color={COLORS.warning}>
            {rule.evidence.filter((c) => c.optional).length} 条 optional
          </PlainTag>
        </span>
      </div>
      <div className={styles.pageDesc}>{rule.description}</div>

      <div className={styles.clauseList}>
        {rule.evidence.map((c, idx) => {
          const signal = c.signal ?? c.metric ?? (c.signal_any ?? []).join(' | ');
          const pct = totalWeight ? (c.weight / totalWeight) * 100 : 0;
          return (
            <div className={styles.clause} key={`${signal}-${idx}`}>
              <div className={styles.clauseHead}>
                <span className={styles.clauseSignal}>{signal}</span>
                {c.kind ? (
                  <PlainTag tiny color={COLORS.inkSecondary}>
                    {c.kind}
                  </PlainTag>
                ) : null}
                {c.layer ? (
                  <PlainTag tiny color={COLORS.inkSecondary}>
                    {c.layer}
                  </PlainTag>
                ) : null}
                {c.op ? (
                  <PlainTag tiny color={COLORS.primary}>
                    {c.op} {c.value ?? ''}
                  </PlainTag>
                ) : null}
                {c.require_increase ? (
                  <PlainTag tiny color={COLORS.warning}>
                    require_increase
                  </PlainTag>
                ) : null}
                {c.status ? (
                  <PlainTag tiny color={COLORS.warning}>
                    status={c.status}
                  </PlainTag>
                ) : null}
                {c.after ? (
                  <PlainTag tiny color={COLORS.layerVm}>
                    after {c.after}
                  </PlainTag>
                ) : null}
                {c.optional ? (
                  <PlainTag tiny color={COLORS.inkTertiary} dashed>
                    optional（缺失不扣分）
                  </PlainTag>
                ) : null}
                {c.require_attribute ? (
                  <PlainTag tiny color={COLORS.inkSecondary}>
                    attributes.{c.require_attribute}
                  </PlainTag>
                ) : null}
                <span style={{ marginLeft: 'auto' }} className={styles.ruleMeta}>
                  weight {c.weight}
                </span>
              </div>
              <div className={styles.weightRow} style={{ marginTop: 5 }}>
                <span
                  style={{
                    height: 5,
                    background: '#eef1f4',
                    border: '1px solid var(--ts-rule)',
                    borderRadius: 1,
                    overflow: 'hidden',
                  }}
                >
                  <span
                    style={{
                      display: 'block',
                      height: '100%',
                      width: `${pct}%`,
                      background: COLORS.primary,
                    }}
                  />
                </span>
                <span style={{ textAlign: 'right', color: 'var(--ts-ink-3)' }}>
                  {pct.toFixed(1)}%
                </span>
              </div>
              <div className={styles.clauseDesc}>{c.description}</div>
            </div>
          );
        })}
      </div>

      <FoldPanel
        title="规则 YAML 结构（关键字段）"
        icon="rule"
        meta={`${rule.rule}.yaml`}
        items={[
          {
            key: 'yaml',
            label: 'rule / evidence / correlation / result 四段',
            children: <pre className={styles.yaml}>{yaml}</pre>,
          },
          {
            key: 'result',
            label: `result.suggestions（${rule.result.suggestions.length} 条处置建议）`,
            children: <SuggestionList suggestions={rule.result.suggestions} fallback={rule.rule} />,
          },
          {
            key: 'correlation',
            label: 'correlation 关联约束',
            children: (
              <div style={{ display: 'grid', gap: 4 }}>
                {Object.entries(rule.correlation).map(([k, v]) => (
                  <div key={k} style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: 10 }}>
                    <span className="ts-mono" style={{ fontSize: 11, color: 'var(--ts-ink-3)' }}>
                      {k}
                    </span>
                    <span className="ts-mono" style={{ fontSize: 11 }}>
                      {Array.isArray(v) ? v.join(', ') : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
