/**
 * TraceSphere 诊断侧接口契约的类型映射。
 *
 * 严格对应 `rca/docs/API.md`（W1 冻结 v1）：
 *   §1 Evidence Item  §3 Evidence Match  §4.1-§4.6 HTTP 响应
 * 本文件是前端唯一的结构真相；所有网络/夹具数据都必须收敛到这里定义的类型。
 * 注意：`match_score` 是「规则证据命中评分」（0–100），**不是概率**。
 */

/* ------------------------------------------------------------------ */
/* §1 基础枚举                                                         */
/* ------------------------------------------------------------------ */

/** 节点/工作负载健康状态（拓扑着色、卡片角标共用） */
export type NodeStatus = 'healthy' | 'warning' | 'critical' | 'unknown';

/** 证据来源类别 */
export type EvidenceKind =
  | 'cgroup'
  | 'ebpf'
  | 'metric'
  | 'app_event'
  | 'log'
  | 'zsvirt'
  | 'topology';

/** 证据所属层级（时间线分层的依据） */
export type EvidenceLayer = 'application' | 'container' | 'vm' | 'zsvirt';

/** 证据严重度 */
export type Severity = 'info' | 'warning' | 'major' | 'critical';

/** 告警状态 */
export type IncidentStatus = 'open' | 'acknowledged' | 'resolved' | 'silenced';

/** 告警来源 */
export type IncidentSource = 'correlation_cluster' | 'rule_scan' | 'fixture';

/** 资源种类 */
export type ResourceKind =
  | 'host'
  | 'vm'
  | 'container'
  | 'service'
  | 'task'
  | 'process'
  | 'gpu'
  | 'cluster'
  | 'zone'
  | 'network'
  | 'datastore'
  | 'image'
  | 'offering'
  | 'volume'
  | (string & {});

/** 数据源实时状态（§6：real / degraded / mock；health 还会返回 off） */
export type SourceMode = 'real' | 'degraded' | 'mock' | 'unavailable' | 'off';

/** Evidence Match 的五个维度标识（§3 冻结） */
export type ScoreDimension =
  | 'rule_match'
  | 'temporal_precedence'
  | 'resource_adjacency'
  | 'signal_strength'
  | 'independent_evidence';

/** 指标数值单位 */
export type MetricUnit =
  | 'count'
  | 'ratio'
  | 'percent'
  | 'ms'
  | 'usec'
  | 'byte'
  | 'bytes_per_sec'
  | 'none';

/* ------------------------------------------------------------------ */
/* §4 通用小对象                                                       */
/* ------------------------------------------------------------------ */

export interface TimeWindow {
  from: string;
  to: string;
  seconds?: number;
}

/** 各取数来源的可用性；key 为来源名（platform / prometheus / fixture …） */
export type SourceStatusMap = Record<string, SourceMode>;

export interface MetricPointRef {
  name: string;
  value: number;
  unit: MetricUnit | string;
}

export interface ResourceRef {
  resource_id: string;
  name: string;
  kind: ResourceKind;
}

/* ------------------------------------------------------------------ */
/* §1 证据模型                                                         */
/* ------------------------------------------------------------------ */

export interface EvidenceItem {
  evidence_id: string;
  /** 归一化信号名，例如 memory.events.oom_kill */
  signal: string;
  kind: EvidenceKind;
  layer: EvidenceLayer;
  resource_id: string;
  resource_name: string;
  correlation_id?: string;
  task_id?: string;
  observed_at: string;
  severity: Severity;
  description: string;
  value?: number;
  baseline?: number;
  unit?: MetricUnit | string;
  source_event_ids?: string[];
  origin?: string;
  mode?: 'real' | 'mock';
  /** 原始事件负载（详情页可展开查看） */
  payload?: Record<string, unknown>;
}

/* ------------------------------------------------------------------ */
/* §4.2 时间线条目（overview / incident / diagnose 共用同一形状）        */
/* ------------------------------------------------------------------ */

export interface TimelineEntry {
  observed_at: string;
  layer: EvidenceLayer;
  resource_id: string;
  resource_name: string;
  signal: string;
  severity: Severity;
  description: string;
  evidence_id?: string;
  incident_id?: string;
}

/* ------------------------------------------------------------------ */
/* §3 Evidence Match 评分明细                                          */
/* ------------------------------------------------------------------ */

export interface ScoreBreakdownItem {
  dimension: ScoreDimension;
  label: string;
  score: number;
  max: number;
  detail: string;
}

/* ------------------------------------------------------------------ */
/* §4.5 处置建议                                                       */
/* ------------------------------------------------------------------ */

export interface Suggestion {
  action: string;
  title: string;
  /** 依据：引用命中的证据事实 */
  basis: string;
  /** 操作：具体执行动作 */
  detail: string;
  /** 风险：执行代价与副作用 */
  risk: string;
}

export interface AlternativeCause {
  rule: string;
  title: string;
  root_cause?: string;
  match_score: number;
  /** 未入选原因（C 侧可补充；fixture 中给出便于讲清排序语义） */
  reason?: string;
}

/* ------------------------------------------------------------------ */
/* §4.5 Diagnosis 对象（核心）                                          */
/* ------------------------------------------------------------------ */

export interface Diagnosis {
  diagnosis_id: string;
  rule: string;
  rule_version: number;
  title: string;
  root_cause: string;
  root_cause_label: string;
  severity: Severity;
  /** Evidence Match 评分 0–100，非概率 */
  match_score: number;
  match_note: string;
  score_breakdown: ScoreBreakdownItem[];
  evidence_ids: string[];
  evidence?: EvidenceItem[];
  suggestions: Suggestion[];
  alternatives?: AlternativeCause[];
  window?: TimeWindow;
  correlation_id?: string;
  /** 命中规则原文的关键结构（诊断页规则库区域使用） */
  rule_definition?: RuleDefinition;
}

/* ------------------------------------------------------------------ */
/* §4.1 拓扑                                                           */
/* ------------------------------------------------------------------ */

export interface TopologyCombo {
  id: string;
  label: string;
  kind: 'host' | 'vm';
  /** null 表示顶层 Combo */
  parent: string | null;
  /** 可选折叠态（前端 depth 控制会重算） */
  collapsed?: boolean;
}

export interface TopologyNode {
  id: string;
  label: string;
  kind: ResourceKind;
  /** 所属 Combo；顶层节点为 null */
  combo?: string | null;
  subtitle?: string;
  status: NodeStatus;
  incident_count: number;
  badges?: string[];
  metrics?: MetricPointRef[];
  /** 资源自身标识（节点 id 与资源 id 通常一致，保留冗余以兼容 task 前缀） */
  resource_id?: string;
}

export type EdgeRelation =
  | 'contains'
  | 'runs_on'
  | 'calls'
  | 'depends_on'
  | 'proxies'
  | 'hosts'
  | string;

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  relation: EdgeRelation;
  label?: string;
  /** 影响路径高亮（详情页子图使用） */
  status?: NodeStatus;
}

export interface LegendItem {
  kind: ResourceKind;
  label: string;
}

export interface TopologyResponse {
  generated_at: string;
  source: SourceStatusMap;
  combos: TopologyCombo[];
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  legend: LegendItem[];
}

/* ------------------------------------------------------------------ */
/* §4.2 健康总览                                                       */
/* ------------------------------------------------------------------ */

export interface WorkloadSignal {
  signal: string;
  layer: EvidenceLayer;
  count: number;
  last_at: string;
  severity: Severity;
}

export type TrendDirection = 'up' | 'down' | 'flat';

export interface WorkloadMetric {
  name: string;
  label: string;
  value: number;
  unit: MetricUnit | string;
  status: NodeStatus;
  trend: TrendDirection;
  /** 可选阈值，用于卡片内联可视化 */
  threshold?: number;
}

export interface WorkloadHealth {
  resource_id: string;
  name: string;
  kind: ResourceKind;
  /** container / service / task 语义细分，例如 tool / inference / agent */
  workload_type?: string;
  status: NodeStatus;
  /** 0–100 展示分（纯展示，不参与 RCA 评分） */
  health_score: number;
  parent?: ResourceRef;
  last_event_at?: string;
  task_failures: number;
  signals?: WorkloadSignal[] | null;
  metrics?: WorkloadMetric[] | null;
}

export interface OverviewSummary {
  resources: number;
  healthy: number;
  warning: number;
  critical: number;
  tasks_total: number;
  tasks_failed: number;
  incidents: number;
  open_alerts: number;
}

export interface OverviewResponse {
  generated_at: string;
  source: SourceStatusMap;
  window: TimeWindow;
  summary: OverviewSummary;
  workloads: WorkloadHealth[];
  timeline: TimelineEntry[];
}

/* ------------------------------------------------------------------ */
/* §4.3 / §4.4 告警                                                    */
/* ------------------------------------------------------------------ */

export interface Incident {
  incident_id: string;
  correlation_id?: string;
  title: string;
  rule: string;
  severity: Severity;
  status: IncidentStatus;
  /** Top-1 诊断的 Evidence Match 评分 */
  match_score: number;
  first_seen_at: string;
  last_seen_at: string;
  focus_resource: ResourceRef;
  evidence_count: number;
  affected_tasks: number;
  summary: string;
  source: IncidentSource;
}

export interface IncidentListResponse {
  generated_at: string;
  count: number;
  incidents: Incident[];
  source?: SourceStatusMap;
}

export interface ImpactScopeItem {
  resource_id: string;
  kind: ResourceKind;
  name: string;
  relation: EdgeRelation;
  depth: number;
  status: NodeStatus;
  detail?: string;
}

export interface Impact {
  focus: ResourceRef;
  counts: {
    tasks: number;
    services: number;
    containers: number;
    [key: string]: number;
  };
  scope: ImpactScopeItem[];
}

export interface SubGraph {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface IncidentDetailResponse {
  incident: Incident;
  window: TimeWindow;
  diagnosis?: Diagnosis | null;
  candidates?: Diagnosis[] | null;
  evidence?: EvidenceItem[] | null;
  timeline?: TimelineEntry[] | null;
  impact: Impact;
  graph: SubGraph;
  source?: SourceStatusMap;
}

/* ------------------------------------------------------------------ */
/* §4.5 POST /api/v1/diagnose                                          */
/* ------------------------------------------------------------------ */

export interface DiagnoseRequest {
  correlation_id?: string;
  resource_id?: string;
  window_seconds?: number;
  top_n?: number;
  from?: string;
  to?: string;
}

export interface DiagnoseResponse {
  window: TimeWindow;
  focus: {
    correlation_id?: string;
    resource_id?: string;
    [key: string]: string | undefined;
  };
  sources: {
    platform?: SourceMode;
    prometheus?: SourceMode;
    evidence_count?: number;
    [key: string]: SourceMode | number | undefined;
  };
  /** 按 match_score 降序 */
  diagnoses?: Diagnosis[] | null;
  evidence?: EvidenceItem[] | null;
  timeline?: TimelineEntry[] | null;
  impact: Impact;
  graph: SubGraph;
}

/* ------------------------------------------------------------------ */
/* §4.6 指标曲线（ECharts）                                             */
/* ------------------------------------------------------------------ */

export interface SeriesThreshold {
  value: number;
  label: string;
  color?: string;
}

/** points 为 [unix_seconds, value] */
export type SeriesPoint = [number, number];

export interface MetricSeries {
  name: string;
  label: string;
  unit: MetricUnit | string;
  points: SeriesPoint[];
  thresholds: SeriesThreshold[];
}

export interface MetricsSeriesResponse {
  resource_id: string;
  window: TimeWindow;
  series: MetricSeries[];
}

/* ------------------------------------------------------------------ */
/* §2 规则定义（YAML 结构，诊断页「规则库」展示）                        */
/* ------------------------------------------------------------------ */

export interface RuleEvidenceClause {
  signal?: string;
  metric?: string;
  signal_any?: string[];
  kind?: EvidenceKind;
  kind_any?: EvidenceKind[];
  layer?: EvidenceLayer;
  weight: number;
  optional?: boolean;
  require_increase?: boolean;
  status?: string;
  match_any?: string[];
  require_attribute?: string;
  op?: string;
  value?: number;
  after?: string;
  description: string;
}

export interface RuleCorrelation {
  same_resource?: boolean;
  same_vm?: boolean;
  time_window?: string;
  require_correlation_id?: boolean;
  link_via_graph?: ResourceKind[];
}

export interface RuleResult {
  root_cause: string;
  label: string;
  suggestions: Suggestion[];
}

export interface RuleDefinition {
  rule: string;
  version: number;
  title: string;
  description: string;
  severity: Severity;
  evidence: RuleEvidenceClause[];
  correlation: RuleCorrelation;
  result: RuleResult;
  /** 规则文件相对路径，展示「配置驱动」用 */
  path?: string;
}

export interface RuleListResponse {
  rules: RuleDefinition[];
}

/* ------------------------------------------------------------------ */
/* §4 / §1 服务元信息                                                  */
/* ------------------------------------------------------------------ */

export interface MetaResponse {
  service?: string;
  version?: string;
  generated_at?: string;
  endpoints?: { method: string; path: string; description: string }[];
  score_dimensions?: { dimension: ScoreDimension; label: string; max: number; formula: string }[];
  signals?: { signal: string; layer: EvidenceLayer; kind: EvidenceKind; source: string }[];
  rules: RuleDefinition[];
}

export interface ServiceHealthSource {
  name: string;
  mode: SourceMode;
  detail?: string;
}

export interface ServiceHealthResponse {
  status: NodeStatus | 'ok' | 'degraded';
  version?: string;
  uptime_seconds?: number;
  /** RCA /health 返回键值映射；fixture_scenarios 是场景名数组，不是来源状态。 */
  sources: {
    platform?: SourceMode;
    prometheus?: SourceMode;
    fixture?: SourceMode;
    fixture_scenarios?: string[];
  };
}

/* ------------------------------------------------------------------ */
/* 前端展示辅助（非接口契约）                                           */
/* ------------------------------------------------------------------ */

export type DataSourceMode = 'api' | 'fixture';

/** 演示场景（Case1 OOM → Case2 CPU → Case3 工具失败 → Case4 GPU 显存耗尽） */
export type ScenarioId = 'case1-oom' | 'case2-cpu' | 'case3-tool-failure' | 'case4-gpu-mock';

export interface Scenario {
  id: ScenarioId;
  index: number;
  label: string;
  title: string;
  correlation_id: string;
  resource_id: string;
  incident_id: string;
  rule: string;
  hint: string;
}

export interface ApiErrorShape {
  message: string;
  path: string;
  mode: DataSourceMode;
  status?: number;
  hint: string;
}
