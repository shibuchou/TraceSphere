/**
 * 演示场景定义：Case1 OOM → Case2 CPU → Case3 工具失败 → Case4 GPU 显存耗尽。
 *
 * fixture 模式下按 scenario 选择对应的夹具文件；api 模式下作为默认查询参数
 * （correlation_id / resource_id）注入，保证一键切换在两种模式下语义一致。
 * 所有 ID 均取自 docs/evidence/*.md 的真实采集串。
 */
import type { Scenario, ScenarioId } from '@/types';

export const SCENARIOS: Scenario[] = [
  {
    id: 'case1-oom',
    index: 1,
    label: 'Case1 · 容器 OOM',
    title: '容器内存耗尽（Container OOM）',
    correlation_id: 'd38fc66c8364',
    resource_id: 'container:7196bcad3bc1',
    incident_id: 'inc-d38fc66c8364',
    rule: 'container_oom',
    hint: 'tool-service 容器 memory.events.oom_kill Δ=4 → task.failed（Δt=2s）',
  },
  {
    id: 'case2-cpu',
    index: 2,
    label: 'Case2 · CPU 争抢',
    title: 'CPU 资源争抢（CPU Resource Contention）',
    correlation_id: 'cf6d4dfcd64a',
    resource_id: 'container:e5d6f856a747',
    incident_id: 'inc-cf6d4dfcd64a',
    rule: 'cpu_contention',
    hint: 'PSI cpu.some 24.17% + nr_throttled 27 → 推理 36.4s 任务超时',
  },
  {
    id: 'case3-tool-failure',
    index: 3,
    label: 'Case3 · 工具失败',
    title: 'Agent 工具调用失败（Agent Tool Failure）',
    correlation_id: '8da4d26c78f6',
    resource_id: 'container:e6eab2f12b53',
    incident_id: 'inc-8da4d26c78f6',
    rule: 'tool_failure',
    hint: 'tool.result status=error（timed out）→ task.failed（Δt=10s）',
  },
  {
    id: 'case4-gpu-mock',
    index: 4,
    label: 'Case4 · GPU 显存耗尽',
    title: 'GPU 显存耗尽（GPU Memory Exhaustion）',
    correlation_id: '85bcc7f9b016',
    resource_id: 'gpu:mock-gpu0',
    incident_id: 'inc-case4-gpu-mock',
    rule: 'gpu_memory_exhaustion',
    hint: 'Mock DCGM 显存占用率 0.995 + gpu.memory.exhausted（降级模拟数据源）',
  },
];

export const DEFAULT_SCENARIO_ID: ScenarioId = 'case1-oom';

export function getScenario(id: string | undefined | null): Scenario {
  return SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[0];
}

export function isScenarioId(value: string | undefined | null): value is ScenarioId {
  return !!value && SCENARIOS.some((s) => s.id === value);
}

/** 供诊断页「示例输入」使用：可一键填充的查询样本 */
export function scenarioSamples(): { label: string; value: string; kind: 'correlation_id' | 'resource_id' }[] {
  return SCENARIOS.flatMap((s) => [
    { label: `${s.label} (correlation_id)`, value: s.correlation_id, kind: 'correlation_id' as const },
    { label: `${s.label} (resource_id)`, value: s.resource_id, kind: 'resource_id' as const },
  ]);
}
