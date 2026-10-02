/**
 * Fixture 适配层（方案 §2.1「降级/回放」）。
 *
 * 职责：把 `src/mocks/*.json` 包装成与 API.md §4 完全一致的响应体，
 * 因此调用方（client.ts）在两种模式下拿到的是**同一套类型**，页面代码零分支。
 *
 * 与真实服务的差异只在「窗口/时间」这类动态字段上：夹具用
 * `generated_at - window_seconds` 计算窗口，并把事件时间整体平移，
 * 使演示时事件始终落在「最近 N 分钟」内，录屏不会出现过期时间戳。
 */
import topologyRaw from '@/mocks/topology.json';
import overviewRaw from '@/mocks/overview.json';
import incidentsRaw from '@/mocks/incidents.json';
import incidentOomRaw from '@/mocks/incident-oom.json';
import incidentCpuRaw from '@/mocks/incident-cpu.json';
import incidentToolFailureRaw from '@/mocks/incident-tool-failure.json';
import incidentGpuRaw from '@/mocks/incident-case4-gpu-mock.json';
import metricsOomRaw from '@/mocks/metrics-series-oom.json';
import metricsCpuRaw from '@/mocks/metrics-series-cpu.json';
import metaRaw from '@/mocks/meta.json';

import { ApiError } from './errors';
import { getScenario, type SCENARIOS } from './scenarios';
import { windowFromGeneratedAt } from '@/utils/format';
import type {
  DiagnoseRequest,
  DiagnoseResponse,
  Incident,
  IncidentDetailResponse,
  IncidentListResponse,
  MetaResponse,
  MetricsSeriesResponse,
  OverviewResponse,
  ScenarioId,
  TopologyResponse,
} from '@/types';

/* ------------------------------------------------------------------ */
/* 夹具读取                                                            */
/* ------------------------------------------------------------------ */

/** 夹具是静态 JSON，加载时一次性定型；结构由 API.md 保证。 */
const topology = topologyRaw as unknown as TopologyResponse;
const overviewBase = overviewRaw as unknown as OverviewResponse;
const incidentsBase = incidentsRaw as unknown as IncidentListResponse;
const meta = metaRaw as unknown as MetaResponse;

const incidentDetails: Record<ScenarioId, IncidentDetailResponse> = {
  'case1-oom': incidentOomRaw as unknown as IncidentDetailResponse,
  'case2-cpu': incidentCpuRaw as unknown as IncidentDetailResponse,
  'case3-tool-failure': incidentToolFailureRaw as unknown as IncidentDetailResponse,
  'case4-gpu-mock': incidentGpuRaw as unknown as IncidentDetailResponse,
};

const incidentFiles: Record<ScenarioId, IncidentDetailResponse> = incidentDetails;

/* ------------------------------------------------------------------ */
/* 时间平移：让「最近 N 分钟」在演示时始终成立                          */
/* ------------------------------------------------------------------ */

/** 夹具中所有事件的锚点时间（= generated_at），平移基准取它。 */
const FIXTURE_ANCHOR = new Date(overviewBase.generated_at).getTime();

function shiftIso(iso: string | undefined, deltaMs: number): string {
  if (!iso) return iso as unknown as string;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  return new Date(t + deltaMs).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/**
 * 把夹具里接近「锚点」的时间平移到「现在」，保留事件之间的相对间隔。
 * 只平移与锚点相差在 ±1 天内的字段，避免误伤固定基线时间。
 */
function shiftTimeFields<T>(value: T, deltaMs: number): T {
  if (deltaMs === 0) return value;
  if (typeof value === 'string') {
    const t = Date.parse(value);
    if (Number.isNaN(t)) return value;
    if (Math.abs(t - FIXTURE_ANCHOR) > 24 * 3600 * 1000) return value;
    return shiftIso(value, deltaMs) as unknown as T;
  }
  if (Array.isArray(value)) {
    return value.map((v) => shiftTimeFields(v, deltaMs)) as unknown as T;
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = shiftTimeFields(v, deltaMs);
    }
    return out as unknown as T;
  }
  return value;
}

/** fixture 模式的时间原点：每次进程启动取一次，避免同一会话内时间跳动。 */
const SESSION_NOW = Date.now();
const SHIFT_MS = SESSION_NOW - FIXTURE_ANCHOR;

function shifted<T>(value: T): T {
  return shiftTimeFields(value, SHIFT_MS);
}

/** 夹具数据在进程内是常量，深拷贝避免调用方就地修改污染后续读取。 */
function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const FIXTURE_LATENCY_MS = 180;

function delay(ms = FIXTURE_LATENCY_MS): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function notFound(path: string, message: string): never {
  throw new ApiError({
    message,
    path,
    mode: 'fixture',
    status: 404,
    hint: '夹具中不存在该资源。请在顶栏切换到对应演示场景（Case1–Case4）。',
  });
}

/* ------------------------------------------------------------------ */
/* 端点实现（与 API.md §4 一一对应）                                   */
/* ------------------------------------------------------------------ */

const sourceOf = (resp: { source?: Record<string, string> }) => ({
  platform: (resp.source?.platform ?? 'mock') as 'mock',
  prometheus: (resp.source?.prometheus ?? 'mock') as 'mock',
  fixture: 'mock' as const,
});

export async function fixtureTopology(): Promise<TopologyResponse> {
  await delay();
  const data = shifted(clone(topology));
  data.generated_at = new Date(SESSION_NOW).toISOString().replace(/\.\d{3}Z$/, 'Z');
  return data;
}

export async function fixtureOverview(windowSeconds = 900): Promise<OverviewResponse> {
  await delay();
  const data = shifted(clone(overviewBase));
  const generatedAt = new Date(SESSION_NOW).toISOString().replace(/\.\d{3}Z$/, 'Z');
  data.generated_at = generatedAt;
  data.window = {
    from: windowFromGeneratedAt(generatedAt, windowSeconds),
    to: generatedAt,
    seconds: windowSeconds,
  };
  // 时间窗收窄时同步裁剪时间线，行为与真实服务一致。
  const fromMs = new Date(data.window.from).getTime();
  data.timeline = data.timeline.filter((e) => new Date(e.observed_at).getTime() >= fromMs);
  return data;
}

export async function fixtureIncidents(): Promise<IncidentListResponse> {
  await delay();
  const data = shifted(clone(incidentsBase));
  data.generated_at = new Date(SESSION_NOW).toISOString().replace(/\.\d{3}Z$/, 'Z');
  data.count = data.incidents.length;
  return data;
}

export async function fixtureIncidentDetail(incidentId: string): Promise<IncidentDetailResponse> {
  await delay();
  const entry = Object.entries(incidentFiles).find(([, detail]) => detail.incident.incident_id === incidentId);
  if (entry) {
    const detail = shifted(clone(entry[1]));
    detail.incident = detail.incident;
    return detail;
  }
  // 非主线告警：从列表中裁剪出可展示的最小详情（证据/时间线留空，页面走空状态）。
  const list = shifted(clone(incidentsBase));
  const incident = list.incidents.find((i) => i.incident_id === incidentId);
  if (!incident) notFound(`/api/v1/incidents/${incidentId}`, `夹具中不存在告警 ${incidentId}`);
  const base = clone(incidentDetails['case3-tool-failure']);
  const generatedAt = new Date(SESSION_NOW).toISOString().replace(/\.\d{3}Z$/, 'Z');
  return {
    incident: incident as Incident,
    window: { from: windowFromGeneratedAt(generatedAt, 900), to: generatedAt, seconds: 900 },
    diagnosis: base.diagnosis,
    candidates: base.candidates,
    evidence: [],
    timeline: [],
    impact: {
      focus: incident.focus_resource,
      counts: { tasks: incident.affected_tasks, services: 0, containers: 1 },
      scope: [],
    },
    graph: { nodes: [], edges: [] },
    source: sourceOf(list),
  };
}

export async function fixtureDiagnose(request: DiagnoseRequest): Promise<DiagnoseResponse> {
  await delay(320);
  const correlationId = request.correlation_id?.trim();
  const resourceId = request.resource_id?.trim();

  let match: IncidentDetailResponse | undefined;
  if (correlationId) {
    match = Object.values(incidentFiles).find((d) => d.incident.correlation_id === correlationId);
  }
  if (!match && resourceId) {
    match = Object.values(incidentFiles).find(
      (d) => d.incident.focus_resource.resource_id === resourceId,
    );
  }
  if (!match) {
    throw new ApiError({
      message: `窗口内没有匹配 "${correlationId || resourceId}" 的关联簇`,
      path: '/api/v1/diagnose',
      mode: 'fixture',
      status: 404,
      hint: '可用的 correlation_id / resource_id 见上方「示例输入」，或切换到对应演示场景。',
    });
  }

  const detail = shifted(clone(match));
  const requestedWindow = request.window_seconds ?? (request.from && request.to ? undefined : 900);
  const generatedAt = new Date(SESSION_NOW).toISOString().replace(/\.\d{3}Z$/, 'Z');
  const window = request.from && request.to
    ? { from: request.from, to: request.to }
    : { from: windowFromGeneratedAt(generatedAt, requestedWindow ?? 900), to: generatedAt, seconds: requestedWindow };

  const topN = request.top_n ?? 3;
  const diagnoses = (detail.candidates ?? []).slice(0, Math.max(1, topN));
  const evidenceIds = new Set(diagnoses.flatMap((d) => d.evidence_ids));
  const evidence = (detail.evidence ?? []).filter((e) => evidenceIds.has(e.evidence_id));

  return {
    window,
    focus: { correlation_id: correlationId, resource_id: resourceId ?? detail.incident.focus_resource.resource_id },
    sources: { platform: 'real', prometheus: 'real', evidence_count: evidence.length },
    diagnoses,
    evidence,
    timeline: detail.timeline ?? [],
    impact: detail.impact,
    graph: detail.graph,
  };
}

export async function fixtureMetricsSeries(resourceId: string): Promise<MetricsSeriesResponse> {
  await delay();
  const normalized = resourceId.includes(':') ? resourceId : `container:${resourceId}`;
  const file =
    normalized === 'container:e5d6f856a747'
      ? metricsCpuRaw
      : normalized === 'container:7196bcad3bc1'
        ? metricsOomRaw
        : null;
  if (!file) {
    notFound(
      `/api/v1/metrics/series?resource_id=${resourceId}`,
      `夹具中没有 ${resourceId} 的指标曲线`,
    );
  }
  const data = shifted(clone(file as unknown as MetricsSeriesResponse));
  const generatedAt = new Date(SESSION_NOW).toISOString().replace(/\.\d{3}Z$/, 'Z');
  data.window = {
    from: windowFromGeneratedAt(generatedAt, 300),
    to: generatedAt,
    seconds: 300,
  } as MetricsSeriesResponse['window'];
  // 采样点整体平移，横轴与「最近 5 分钟」对齐。
  const deltaSec = Math.floor(SHIFT_MS / 1000);
  data.series = data.series.map((s) => ({
    ...s,
    points: s.points.map(([t, v]) => [t + deltaSec, v] as [number, number]),
  }));
  return data;
}

export async function fixtureMeta(): Promise<MetaResponse> {
  await delay(80);
  return clone(meta);
}

/** fixture 模式下的「服务健康」：始终可用，来源标注为 mock。 */
export async function fixtureServiceHealth(): Promise<{
  status: string;
  version: string;
  sources: { name: string; mode: 'mock' | 'real'; detail: string }[];
}> {
  await delay(60);
  return {
    status: 'mock',
    version: meta.version ?? '1.0.0',
    sources: [
      { name: 'fixture', mode: 'mock', detail: `本地夹具 · ${Object.keys(incidentFiles).length} 个场景可回放` },
      { name: 'platform', mode: 'real', detail: '夹具内嵌真实采集值（2026-09-20 演练）' },
      { name: 'prometheus', mode: 'real', detail: '夹具内嵌 cAdvisor 采样点' },
    ],
  };
}

/** 诊断页「示例输入」用：夹具里全部可诊断的 correlation / resource。 */
export function fixtureScenarioIndex(): { label: string; value: string; kind: 'correlation_id' | 'resource_id' }[] {
  return (Object.keys(incidentFiles) as ScenarioId[]).flatMap((id) => {
    const s = getScenario(id);
    return [
      { label: `${s.label} (correlation_id)`, value: s.correlation_id, kind: 'correlation_id' as const },
      { label: `${s.label} (resource_id)`, value: s.resource_id, kind: 'resource_id' as const },
    ];
  });
}

/** 供拓扑页做「聚焦某资源」的夹具索引（不参与渲染，仅便于校验 ID）。 */
export const FIXTURE_RESOURCE_IDS: string[] = topology.nodes.map((n) => n.id);

export type FixtureScenarioList = typeof SCENARIOS;
