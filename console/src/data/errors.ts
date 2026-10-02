/**
 * 统一错误类型：携带请求路径、模式与可执行的修复指引。
 * 页面错误态直接消费该对象，不解析字符串。
 */
import type { ApiErrorShape, DataSourceMode } from '@/types';

export class ApiError extends Error implements ApiErrorShape {
  readonly path: string;
  readonly mode: DataSourceMode;
  readonly status?: number;
  readonly hint: string;

  constructor(shape: ApiErrorShape) {
    super(shape.message);
    this.name = 'ApiError';
    this.path = shape.path;
    this.mode = shape.mode;
    this.status = shape.status;
    this.hint = shape.hint;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function toApiError(value: unknown, fallbackPath = ''): ApiError {
  if (isApiError(value)) return value;
  const message = value instanceof Error ? value.message : String(value);
  return new ApiError({
    message,
    path: fallbackPath,
    mode: 'api',
    hint: '未知错误，请重试或切换到 fixture 模式。',
  });
}
