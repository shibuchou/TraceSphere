// 夹具自检：用纯 Node 校验 src/mocks/*.json 的内部一致性与契约字段完整性。
// 不依赖构建工具链，可在受限环境下直接运行：node scripts/check-fixtures.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const load = (name) => JSON.parse(readFileSync(join(root, 'src/mocks', name), 'utf8'));

let failures = 0;
const ok = (msg) => console.log(`  PASS  ${msg}`);
const bad = (msg) => {
  failures += 1;
  console.log(`  FAIL  ${msg}`);
};
const check = (cond, msg) => (cond ? ok(msg) : bad(msg));

const topology = load('topology.json');
const overview = load('overview.json');
const incidents = load('incidents.json');
const meta = load('meta.json');
const details = {
  'case1-oom': load('incident-oom.json'),
  'case2-cpu': load('incident-cpu.json'),
  'case3-tool-failure': load('incident-tool-failure.json'),
  'case4-gpu-mock': load('incident-case4-gpu-mock.json'),
};
const series = {
  'case1-oom': load('metrics-series-oom.json'),
  'case2-cpu': load('metrics-series-cpu.json'),
};

console.log('\n[1] 拓扑结构');
const nodeIds = new Set(topology.nodes.map((n) => n.id));
const comboIds = new Set(topology.combos.map((c) => c.id));
check(nodeIds.size === topology.nodes.length, `节点 ID 唯一（${nodeIds.size}）`);
check(
  topology.nodes.every((n) => n.combo === null || comboIds.has(n.combo)),
  '每个节点的 combo 都在 combos 中声明',
);
check(
  topology.combos.every((c) => c.parent === null || comboIds.has(c.parent)),
  'combo 的 parent 都在 combos 中声明（host → vm 嵌套成立）',
);
check(
  topology.edges.every((e) => nodeIds.has(e.source) && nodeIds.has(e.target)),
  '每条边的 source / target 都是已声明节点',
);
check(
  topology.nodes.every((n) => ['healthy', 'warning', 'critical', 'unknown'].includes(n.status)),
  '节点 status 取值合法',
);
check(
  topology.nodes.every((n) => Number.isInteger(n.incident_count) && n.incident_count >= 0),
  '节点 incident_count 为非负整数（角标渲染前提）',
);
const hostCombo = topology.combos.find((c) => c.kind === 'host');
const vmCombo = topology.combos.find((c) => c.kind === 'vm');
check(Boolean(hostCombo && vmCombo && vmCombo.parent === hostCombo.id), '存在 host Combo → vm Combo 两级嵌套');
check(
  topology.nodes.filter((n) => n.kind === 'vm').every((n) => n.combo === vmCombo.id),
  'VM 节点挂在 VM Combo 下',
);
check(
  topology.nodes.some((n) => n.kind === 'container') &&
    topology.nodes.filter((n) => n.kind === 'container').every((n) => n.combo === vmCombo.id),
  '容器 / 服务 / 任务节点均挂在 VM Combo 下',
);
check(
  topology.nodes.some((n) => n.kind === 'gpu' && n.id === 'gpu:mock-gpu0'),
  '拓扑包含 Case4 的 GPU 节点',
);

console.log('\n[2] 概览');
check(
  overview.summary.resources === topology.nodes.length,
  `summary.resources(${overview.summary.resources}) === 拓扑节点数(${topology.nodes.length})`,
);
const byStatus = topology.nodes.reduce((acc, n) => ((acc[n.status] = (acc[n.status] ?? 0) + 1), acc), {});
check(
  overview.summary.healthy === (byStatus.healthy ?? 0) &&
    overview.summary.warning === (byStatus.warning ?? 0) &&
    overview.summary.critical === (byStatus.critical ?? 0),
  `summary 健康分布与拓扑一致（健康${byStatus.healthy ?? 0}/警告${byStatus.warning ?? 0}/严重${byStatus.critical ?? 0}）`,
);
check(
  overview.workloads.every((w) => w.signals.length + w.metrics.length > 0),
  '每个工作负载卡片至少有信号或指标（避免空卡片）',
);
check(
  overview.workloads.every((w) => w.health_score >= 0 && w.health_score <= 100),
  'health_score 落在 0–100',
);
check(
  overview.timeline.every((e) => ['application', 'container', 'vm', 'zsvirt'].includes(e.layer)),
  `时间线 ${overview.timeline.length} 条事件的 layer 合法（分层着色前提）`,
);
const layersUsed = new Set(overview.timeline.map((e) => e.layer));
check(layersUsed.size >= 3, `时间线覆盖 ${layersUsed.size} 个层级（应用/容器/虚拟机/云平台）`);

console.log('\n[3] 告警列表');
check(incidents.count === incidents.incidents.length, `count(${incidents.count}) 与数组长度一致`);
const incidentIds = new Set(incidents.incidents.map((i) => i.incident_id));
check(
  Object.values(details).every((d) => incidentIds.has(d.incident.incident_id)),
  '四个场景详情的 incident_id 都在告警列表中',
);
check(
  incidents.incidents.every((i) =>
    ['correlation_cluster', 'rule_scan', 'fixture'].includes(i.source),
  ),
  'incident.source 取值合法',
);

console.log('\n[4] 告警详情 + 诊断');
for (const [scene, d] of Object.entries(details)) {
  const evIds = new Set(d.evidence.map((e) => e.evidence_id));
  const evidenceComplete = d.evidence.every(
    (e) =>
      e.evidence_id &&
      e.signal &&
      e.layer &&
      e.resource_id &&
      e.observed_at &&
      e.severity &&
      e.description &&
      typeof e.kind === 'string',
  );
  check(evidenceComplete, `${scene}: 所有证据含 evidence_id/signal/kind/layer/resource_id/observed_at/severity/description`);
  check(
    d.diagnosis.evidence_ids.every((id) => evIds.has(id)),
    `${scene}: 诊断引用的 evidence_ids 都在证据列表中`,
  );
  const sum = d.diagnosis.score_breakdown.reduce((acc, x) => acc + x.score, 0);
  const max = d.diagnosis.score_breakdown.reduce((acc, x) => acc + x.max, 0);
  check(
    d.diagnosis.score_breakdown.length === 5,
    `${scene}: score_breakdown 为 5 个维度（${d.diagnosis.score_breakdown.map((x) => x.dimension).join('/')}）`,
  );
  check(max === 100, `${scene}: 五维度上限合计 ${max}（应为 100）`);
  check(
    sum === d.diagnosis.match_score,
    `${scene}: 五维度得分合计 ${sum} === match_score ${d.diagnosis.match_score}`,
  );
  check(
    Boolean(d.diagnosis.match_note && /非概率/.test(d.diagnosis.match_note)),
    `${scene}: match_note 明确声明「非概率」`,
  );
  check(
    d.diagnosis.suggestions.every((s) => s.basis && s.detail && s.risk && s.action && s.title),
    `${scene}: 每条处置建议都含 action/title/basis/detail/risk 五字段`,
  );
  const scores = d.candidates.map((c) => Math.round(c.match_score));
  check(
    d.candidates.length >= 1 && scores.every((v, i) => i === 0 || v <= scores[i - 1]),
    `${scene}: 候选严格按 match_score 降序（${scores.join(' ≥ ')}）`,
  );
  check(
    d.timeline.every((t) => t.resource_id && t.signal && t.observed_at),
    `${scene}: 时间线字段完整（${d.timeline.length} 条）`,
  );
  check(
    d.impact.scope.every((s) => s.resource_id && s.kind && s.depth >= 0),
    `${scene}: 影响范围条目字段完整（${d.impact.scope.length} 条）`,
  );
  check(
    d.graph.nodes.every((n) => n.status && n.kind && n.label),
    `${scene}: 子图节点可渲染（${d.graph.nodes.length} 节点 / ${d.graph.edges.length} 边）`,
  );
  check(
    d.graph.edges.every(
      (e) => d.graph.nodes.some((n) => n.id === e.source) && d.graph.nodes.some((n) => n.id === e.target),
    ),
    `${scene}: 子图边两端都在子图节点内`,
  );
  const scenarioResource = d.incident.focus_resource.resource_id;
  check(
    d.impact.focus.resource_id === scenarioResource,
    `${scene}: impact.focus 与 incident.focus_resource 一致`,
  );
}

console.log('\n[5] 指标曲线');
for (const [scene, s] of Object.entries(series)) {
  check(s.series.length > 0, `${scene}: 含 ${s.series.length} 条序列`);
  check(
    s.series.every((x) => x.points.length >= 2 && x.points.every((p) => Array.isArray(p) && p.length === 2)),
    `${scene}: points 均为 [unix_seconds, value] 二元组`,
  );
  check(
    s.series.every((x) => x.points.every((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]))),
    `${scene}: 采样点数值有限且可绘制`,
  );
  const ascending = s.series.every((x) => x.points.every((p, i) => i === 0 || p[0] >= x.points[i - 1][0]));
  check(ascending, `${scene}: 时间轴单调递增（ECharts time 轴前提）`);
  check(
    s.series.some((x) => x.thresholds.length > 0),
    `${scene}: 至少一条序列带阈值线`,
  );
}

console.log('\n[6] 规则库（meta.json）');
const expectedRules = ['container_oom', 'cpu_contention', 'tool_failure', 'gpu_memory_exhaustion'];
check(
  meta.rules.length === expectedRules.length && expectedRules.every((name) => meta.rules.some((rule) => rule.rule === name)),
  `规则覆盖 ${meta.rules.length} 条（${expectedRules.join(' / ')}）`,
);
check(
  meta.rules.every((r) => r.evidence.length > 0 && r.result.suggestions.length > 0),
  '每条规则都有 evidence 条款与 result.suggestions',
);
check(
  meta.rules.every((r) => r.evidence.every((c) => typeof c.weight === 'number' && c.description)),
  '每条条款都有 weight 与 description（权重条形图前提）',
);
check(
  meta.rules.every((r) => r.evidence.some((c) => c.signal) && r.evidence.some((c) => c.metric || c.signal)),
  '条款包含 signal 型与 metric 型（覆盖两种匹配语义）',
);
check(
  meta.score_dimensions.length === 5 && meta.score_dimensions.reduce((a, d) => a + d.max, 0) === 100,
  '评分维度 5 个、上限合计 100',
);
check(
  meta.rules.every((r) => r.correlation && r.result.root_cause),
  '每条规则含 correlation 段与 result.root_cause',
);

console.log(
  failures === 0
    ? '\n✅ 夹具自检全部通过（数据与 API.md 契约、真实证据链一致）\n'
    : `\n❌ 夹具自检失败 ${failures} 项\n`,
);
process.exit(failures === 0 ? 0 : 1);
