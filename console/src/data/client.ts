/**
 * 数据访问层（方案 §2.1 降级/回放）。
 *
 * 两种模式，调用方零分支：
 *   - `api`     ：请求真实诊断服务。相对路径 `/api/v1` 由 dev server（vite.config.ts
 *                 proxy）或生产 nginx 代理到 `rca-serve --listen :8010`，规避 CORS；
 *                 也可用 `VITE_RCA_BASE_URL` 直连。
 *   - `fixture` ：读取 `src/mocks/*.json`，响应结构与 API.md §4 完全一致。
 *
 * 关键约定：**api 模式失败时绝不静默降级**。错误会带着「如何切到 fixture」的
 * 指引抛给页面，由页面渲染错误态——评审必须一眼看出数据是真实还是回放。
 */
import { ApiError } from './errors';
import * as fixtures from './fixtures';
import type {
  DiagnoseRequest,
  DiagnoseResponse,
  DataSourceMode,
  IncidentDetailResponse,
  IncidentListResponse,
  IncidentStatus,
  MetaResponse,
  MetricsSeriesResponse,
  OverviewResponse,
  ServiceHealthResponse,
  TopologyResponse,
} from '@/types';

const RAW_SOURCE = (import.meta.env.VITE_DATA_SOURCE ?? 'api').trim().toLowerCase();
export const DATA_SOURCE: DataSourceMode = RAW_SOURCE === 'fixture' ? 'fixture' : 'api';

/** 尾部不带 `/` 的 base；为空时使用相对路径 `/api/v1`（推荐，走反向代理）。 */
const RAW_BASE = (import.meta.env.VITE_RCA_BASE_URL ?? '').trim().replace(/\/+$/, '');
export const API_BASE = RAW_BASE ? RAW_BASE : '/api/v1';
export const API_BASE_IS_ABSOLUTE = /^https?:\/\//i.test(RAW_BASE);

export const PLATFORM_BASE = (import.meta.env.VITE_PLATFORM_BASE_URL ?? 'http://127.0.0.1:8000')
  .trim()
  .replace(/\/+$/, '');

const DEFAULT_TIMEOUT_MS = 8000;
const fixtureIncidentStatuses = new Map<string, IncidentStatus>();

function applyFixtureStatus<T extends { incident_id: string; status: IncidentStatus }>(incident: T): T {
  const status = fixtureIncidentStatuses.get(incident.incident_id);
  return status ? { ...incident, status } : incident;
}

/** 可选静态令牌（诊断服务放开 CORS，通常无需鉴权）。 */
function authHeaders(): Record<string, string> {
  try {
    const token = window.localStorage.getItem('tracesphere.auth_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

function describeNetworkFailure(path: string, cause: unknown): ApiError {
  const raw = cause instanceof Error ? cause.message : String(cause);
  const isTimeout = /abort|timeout/i.test(raw);
  const isRefused = /failed to fetch|network|load failed|econnrefused/i.test(raw);
  const message = isTimeout
    ? `请求超时（>${DEFAULT_TIMEOUT_MS / 1000}s）：${path}`
    : isRefused
      ? `无法连接诊断服务：${path}`
      : `请求失败：${path}（${raw}）`;
  return new ApiError({
    message,
    path,
    mode: 'api',
    hint: `请确认诊断服务已启动（rca-serve --listen :8010，当前代理目标 ${API_BASE}），或在顶栏把数据源切到 fixture 用本地夹具完整演示。`,
  });
}

export interface RequestOptions {
  method?: 'GET' | 'POST';
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
    }
  }
  const finalPath = `${url.pathname}${url.search}`;

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });

  try {
    const response = await fetch(url.toString(), {
      method,
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}), ...authHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new ApiError({
        message: `诊断服务返回 ${response.status} ${response.statusText}：${finalPath}`,
        path: finalPath,
        mode: 'api',
        status: response.status,
        hint:
          response.status === 404
            ? '该端点或资源在服务端不存在。请核对 API.md §4 契约，或切换到 fixture 模式。'
            : response.status >= 500
              ? '服务端内部错误：请查看 rca-serve 日志；也可临时切到 fixture 模式继续演示。'
              : `${text.slice(0, 200) || '无响应体'}`,
      });
    }

    return (await response.json()) as T;
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    if ((cause as Error)?.name === 'AbortError' && signal?.aborted) {
      throw new ApiError({
        message: '请求已取消',
        path: finalPath,
        mode: 'api',
        hint: '视图切换或参数变更导致的取消，可忽略。',
      });
    }
    throw describeNetworkFailure(finalPath, cause);
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

/* ------------------------------------------------------------------ */
/* 对页面暴露的统一接口                                                */
/* ------------------------------------------------------------------ */

export const api = {
  mode: DATA_SOURCE,
  base: API_BASE,

  getTopology(options?: { signal?: AbortSignal }): Promise<TopologyResponse> {
    if (DATA_SOURCE === 'fixture') return fixtures.fixtureTopology();
    return request<TopologyResponse>('/topology', { signal: options?.signal });
  },

  getOverview(windowSeconds: number, options?: { signal?: AbortSignal }): Promise<OverviewResponse> {
    if (DATA_SOURCE === 'fixture') return fixtures.fixtureOverview(windowSeconds);
    return request<OverviewResponse>('/overview', {
      query: { window_seconds: windowSeconds },
      signal: options?.signal,
    });
  },

  getIncidents(options?: { signal?: AbortSignal }): Promise<IncidentListResponse> {
    if (DATA_SOURCE === 'fixture') {
      return fixtures.fixtureIncidents().then((data) => ({
        ...data,
        incidents: data.incidents.map(applyFixtureStatus),
      }));
    }
    return request<IncidentListResponse>('/incidents', { signal: options?.signal });
  },

  getIncident(id: string, options?: { signal?: AbortSignal }): Promise<IncidentDetailResponse> {
    if (DATA_SOURCE === 'fixture') {
      return fixtures.fixtureIncidentDetail(id).then((detail) => ({
        ...detail,
        incident: applyFixtureStatus(detail.incident),
      }));
    }
    return request<IncidentDetailResponse>(`/incidents/${encodeURIComponent(id)}`, {
      signal: options?.signal,
    });
  },

  /** 告警运营：静默 / 确认 / 已处理 / 恢复（最小实现，状态落盘于诊断服务）。 */
  setIncidentStatus(
    id: string,
    action: 'silence' | 'acknowledge' | 'resolve' | 'open',
    options?: { signal?: AbortSignal },
  ): Promise<{ incident_id: string; status: string }> {
    if (DATA_SOURCE === 'fixture') {
      const status =
        action === 'silence' ? 'silenced' : action === 'acknowledge' ? 'acknowledged' : action === 'resolve' ? 'resolved' : 'open';
      fixtureIncidentStatuses.set(id, status);
      return Promise.resolve({ incident_id: id, status });
    }
    return request<{ incident_id: string; status: string }>(`/incidents/${encodeURIComponent(id)}/status`, {
      method: 'POST',
      body: { action },
      signal: options?.signal,
    });
  },

  diagnose(payload: DiagnoseRequest, options?: { signal?: AbortSignal }): Promise<DiagnoseResponse> {
    if (DATA_SOURCE === 'fixture') return fixtures.fixtureDiagnose(payload);
    return request<DiagnoseResponse>('/diagnose', {
      method: 'POST',
      body: payload,
      signal: options?.signal,
      timeoutMs: 20000,
    });
  },

  getMetricsSeries(resourceId: string, windowSeconds: number, options?: { signal?: AbortSignal }): Promise<MetricsSeriesResponse> {
    if (DATA_SOURCE === 'fixture') return fixtures.fixtureMetricsSeries(resourceId);
    return request<MetricsSeriesResponse>('/metrics/series', {
      query: { resource_id: resourceId, window_seconds: windowSeconds },
      signal: options?.signal,
    });
  },

  getMeta(options?: { signal?: AbortSignal }): Promise<MetaResponse> {
    if (DATA_SOURCE === 'fixture') return fixtures.fixtureMeta();
    return request<MetaResponse>('/meta', { signal: options?.signal });
  },

  /** 数据源可用性：api 模式探 /health，fixture 模式返回本地回放说明。 */
  async getServiceHealth(options?: { signal?: AbortSignal }): Promise<ServiceHealthResponse> {
    if (DATA_SOURCE === 'fixture') {
      const h = await fixtures.fixtureServiceHealth();
      return {
        status: 'degraded',
        version: h.version,
        sources: Object.fromEntries(h.sources.map((source) => [source.name, source.mode])),
      };
    }
    return request<ServiceHealthResponse>('/health', { signal: options?.signal, timeoutMs: 4000 });
  },
};

export type ApiClient = typeof api;
