/**
 * 设计令牌的唯一出处。
 *
 * CSS 侧通过 `src/styles/global.css` 的 `:root` 变量镜像同一套值；
 * 需要在 JS 中取色的地方（G6 拓扑、ECharts 曲线）从这里读，避免两处漂移。
 */

export const COLORS = {
  /** 主色：工程蓝（唯一强调色，用于导航选中、主按钮、当前窗口） */
  primary: '#2B5B8F',
  primarySoft: '#E8F0F8',

  ink: '#0F1318',
  inkSecondary: '#4A545F',
  inkTertiary: '#7C8794',
  paper: '#F6F7F9',
  surface: '#FFFFFF',
  rule: '#DFE3E8',
  ruleStrong: '#C3CAD3',

  /** 状态色：仅用于 healthy / warning / critical / unknown 四态 */
  healthy: '#2E8B57',
  healthySoft: '#E7F3EC',
  warning: '#D97B10',
  warningSoft: '#FDF1E0',
  critical: '#C0392B',
  criticalSoft: '#FBE9E7',
  unknown: '#7C8794',
  unknownSoft: '#EEF0F3',

  /** 层级色：时间线分层着色（应用 / 容器 / 虚拟机 / 云平台） */
  layerApplication: '#2B5B8F',
  layerContainer: '#1F7A8C',
  layerVm: '#7A5EA6',
  layerZsvirt: '#8A6D3B',
} as const;

export const MONO_FONT =
  'ui-monospace, "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace';

export const SANS_FONT =
  '"Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif';

export const STATUS_TEXT: Record<string, string> = {
  healthy: '健康',
  warning: '警告',
  critical: '严重',
  unknown: '未知',
};

export const SEVERITY_TEXT: Record<string, string> = {
  info: '提示',
  warning: '警告',
  major: '重要',
  critical: '严重',
};

export const LAYER_TEXT: Record<string, string> = {
  application: '应用层',
  container: '容器层',
  vm: '虚拟机层',
  zsvirt: '云平台层',
};

export const KIND_TEXT: Record<string, string> = {
  host: '宿主机',
  vm: '虚拟机',
  container: '容器',
  service: 'AI 服务',
  task: 'Agent 任务',
  process: '进程',
  gpu: 'GPU',
  cluster: '集群',
  zone: '可用区',
  network: '网络',
  datastore: '数据存储',
  image: '镜像',
  offering: '计算规格',
  volume: '云硬盘',
};

export const EVIDENCE_KIND_TEXT: Record<string, string> = {
  cgroup: 'cgroup v2',
  ebpf: 'eBPF',
  metric: '指标',
  app_event: '应用事件',
  log: '日志',
  zsvirt: 'ZSvirt',
  topology: '拓扑',
};

export const INCIDENT_STATUS_TEXT: Record<string, string> = {
  open: '未处理',
  acknowledged: '已确认',
  resolved: '已恢复',
  silenced: '已静默',
};

export const SOURCE_TEXT: Record<string, string> = {
  real: '真实',
  degraded: '降级',
  mock: '回放',
  unavailable: '不可用',
  off: '未启用',
};

export const TREND_TEXT: Record<string, string> = {
  up: '↑',
  down: '↓',
  flat: '→',
};

export const SCORE_DIMENSION_TEXT: Record<string, string> = {
  rule_match: '规则证据命中',
  temporal_precedence: '时间优先性',
  resource_adjacency: '资源邻接度',
  signal_strength: '信号强度',
  independent_evidence: '独立证据数',
};

export const LAYER_ORDER = ['zsvirt', 'vm', 'container', 'application'] as const;

export const LAYER_COLOR: Record<string, string> = {
  application: COLORS.layerApplication,
  container: COLORS.layerContainer,
  vm: COLORS.layerVm,
  zsvirt: COLORS.layerZsvirt,
};

export const STATUS_COLOR: Record<string, string> = {
  healthy: COLORS.healthy,
  warning: COLORS.warning,
  critical: COLORS.critical,
  unknown: COLORS.unknown,
};

export const SEVERITY_COLOR: Record<string, string> = {
  info: COLORS.inkTertiary,
  warning: COLORS.warning,
  major: '#C25E00',
  critical: COLORS.critical,
};
