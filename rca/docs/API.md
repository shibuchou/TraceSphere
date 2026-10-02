# TraceSphere 诊断侧接口契约（成员 C，W1 冻结 v1）

> 本文档冻结 C 侧三件事：**规则定义结构**、**证据模型**、**诊断服务 HTTP API**。
> 上游（B 的 platform、A 的采集）按各自契约提供数据；C 只消费，不改上游结构。
> 冻结日期：2026-09-21 ｜ 对应方案 `方案初版.md` §5.4 / §6.1 / §6.3 / §6.5

---

## 0. 边界（方案 §6.1）

```text
B： "这些事件之间有关联。"                     → 关联簇（结构化证据集合，含 evidence_id）
C： "根据这些关联，最可能的问题是什么，
      证据是什么，影响谁，该怎么处理。"          → 诊断（根因候选 Top-N + 影响范围 + 处置建议）
```

C **不**重复采集、**不**重复关联、**不**自研 Alertmanager 已有的 grouping/silence/inhibition/dedup。

---

## 1. 证据模型（Evidence Item）

C 的内部统一证据模型，来源于三个 adapter，字段对齐 B 的 `evidence` 表（`platform/README.md`）：

```json
{
  "evidence_id": "ev-0001 | platform 的 evidence_id",
  "signal": "memory.events.oom_kill",
  "kind": "cgroup | ebpf | metric | app_event | log | zsvirt | topology",
  "layer": "application | container | vm | zsvirt",
  "resource_id": "container:7196bcad3bc1...",
  "resource_name": "tool-service",
  "correlation_id": "d38fc66c8364",
  "task_id": "task-1789892737-9d8d72",
  "observed_at": "2026-09-20T08:25:37Z",
  "severity": "info | warning | major | critical",
  "description": "memory.events.oom_kill Δ=4 [cgroup] on tool-service",
  "value": 4.0,
  "baseline": 0.0,
  "unit": "count | ratio | percent | ms | usec",
  "source_event_ids": ["evt-..."],
  "origin": "cgroup | ebpf | app | cadvisor | zsvirt",
  "mode": "real | mock"
}
```

**证据命名约定**（与 A 的事件命名对齐，`signal` 为匹配键）：

| layer | signal 示例 | 来源 |
|---|---|---|
| application | `task.started` `tool.call` `tool.result` `task.failed` `task.finished` `inference.result` | agent-service AppEvent |
| container | `memory.events.oom_kill` `memory.current_ratio` `cpu.stat.nr_throttled` `cpu.cfs.throttled_periods` `container.restart` `oom.ebpf` | cgroup v2 / cAdvisor / vm-agent |
| vm | `psi_cpu_some_avg10` `psi_cpu_full_avg10` `psi_mem_some_avg10` `psi_io_some_avg10` `tcp.retransmit` `process.exec` `process.exit` | vm-agent |
| zsvirt | `zsvirt.alarm` `zsvirt.event` | ZSvirt REST（B） |

> 指标类证据的 `signal` 由 C 的 Prometheus adapter 归一化产生，映射表见 §5。

---

## 2. 规则定义（YAML，W1 冻结）

文件位置：`rca/rules/*.yaml`；四段结构固定为 `rule / evidence / correlation / result`（方案 §6.3）。
新增规则 = 新增 YAML，**不改引擎代码**。

```yaml
rule: container_oom                 # 唯一 ID
version: 1
title: 容器内存耗尽（Container OOM）
description: 容器 cgroup 内存打到 limit 并被内核 OOM kill，导致其上 Agent 任务失败
severity: critical

evidence:                           # 证据条款列表，权重和为 100（引擎会归一化）
  - signal: memory.events.oom_kill  # 事件型证据：匹配 event_type / evidence.signal
    kind: cgroup                    # 可选：限定证据来源类别
    layer: container
    weight: 35
    require_increase: true          # 需要窗口内增量 > 0
    description: cgroup v2 OOM 计数增量 > 0

  - metric: memory.current_ratio    # 指标型证据：由 Prometheus / cgroup adapter 提供
    op: ">"
    value: 0.95
    weight: 20
    description: memory.current / memory.max > 0.95

  - signal: oom.ebpf                # 可选证据（内核 hook 不可用时缺失，不阻塞闭环）
    kind: ebpf
    weight: 20
    optional: true
    description: eBPF OOM kill 事件

  - signal: task.failed
    kind: app_event
    weight: 15
    after: memory.events.oom_kill    # 时间优先性：该证据必须晚于指定证据
    description: OOM 之后 Agent 任务失败

correlation:                        # 关联约束（由 B 的关联簇满足 / C 侧校验）
  same_resource: true
  time_window: 5s
  require_correlation_id: false

result:
  root_cause: container_memory_exhausted
  label: 容器 memory limit 与实际需求不匹配（或应用内存泄漏）
  suggestions:
    - action: adjust_memory_limit
      title: 调整容器 memory limit
      basis: memory.current/max > 0.95 且 memory.events.oom_kill 增量 > 0
      detail: 将该容器 memory limit 提高到峰值 working_set 的 1.3 倍以上
      risk: 提高 limit 会挤占同 VM 其他容器内存，需同步确认 VM 余量
```

**字段语义**

| 字段 | 说明 |
|---|---|
| `evidence[].signal` / `[].metric` / `[].signal_any` | 三选一：单信号条款 / 指标条款 / 多信号任一命中条款 |
| `kind` / `kind_any` | 可选：限定证据来源类别（`cgroup/ebpf/metric/app_event/log/zsvirt/topology`） |
| `layer` | 可选：限定层级（`application/container/vm/zsvirt`），用于时间线分层 |
| `weight` | 条款权重（相对值，引擎按 Σ 归一化到 `rule_match` 维度） |
| `optional` | 缺失不计入分母，也不扣分（用于 eBPF / 日志这类可选证据） |
| `require_increase` | 事件计数型条款：窗口内出现增量（Δ>0）才算命中 |
| `status` | 可选：要求证据 `payload.status` 等于给定值（如 `error`） |
| `match_any` | 可选：证据描述 / `payload.reason` / `payload.error` 命中任一子串（不区分大小写） |
| `require_attribute` | 可选：证据 `payload.attributes` 必须含该键（如工具调用的 `target`） |
| `op` / `value` | 指标阈值比较：`> >= < <= == !=`；`increase_gt` 表示窗口内增量大于阈值 |
| `after` | 时间优先性：本条款证据必须晚于另一条款证据（`rule_match` 之外的独立维度） |
| `correlation.same_resource` | 要求证据落在同一 `resource_id` |
| `correlation.same_vm` | 允许跨容器，但要求同属一个 VM（CPU 争抢场景） |
| `correlation.time_window` | 关联时间窗（默认 5s，与方案 §5.6 一致） |
| `correlation.require_correlation_id` | 是否要求簇携带应用层锚点 |
| `result.root_cause` / `label` / `suggestions` | 根因标识、中文解释、处置建议（每条含 `basis` 依据 + `risk` 风险） |

> 规则文件已交付：`rca/rules/oom.yaml`、`rca/rules/cpu.yaml`、`rca/rules/tool_failure.yaml`。
> 引擎结构体：`rca/internal/rule/rule.go`（`Rule / EvidenceClause / Correlation / Result`）。

---

## 3. Evidence Match Score（方案 §6.3 五个维度，0–100）

```text
Evidence Match = Rule Match（规则证据命中）
               + Temporal Precedence（时间优先性）
               + Resource Adjacency（资源邻接度）
               + Signal Strength（信号强度）
               + Independent Evidence Count（独立证据数）
```

| 维度 | 上限 | 计算 |
|---|---|---|
| `rule_match` | 55 | Σ(命中条款权重) / Σ(参与条款权重) × 55 |
| `temporal_precedence` | 15 | 满足 `after` 约束的比例 × 15；**规则未定义 `after` 时该维度 `max=0`（不适用，不参与归一化）** |
| `resource_adjacency` | 10 | 按资源图距离加权：同一资源 1.0、一跳邻接 0.9、同 VM/服务链 ≤3 跳 0.7、无关 0.2；`same_resource: true` 且存在无关资源证据时置 0 |
| `signal_strength` | 10 | 主证据 severity 基础分（critical 7 / major 5 / warning 3 / info 1）+ min(3, 额外证据数) |
| `independent_evidence` | 10 | 独立证据类别数（cgroup/ebpf/metric/app_event/log/topology）：≥3 得满分，2 得 5，1 得 2 |

**归一化**：`match_score = min(100, Σ各维度得分 / Σ适用维度上限 × 100)`，
其中 `Σ适用维度上限 = 55 + (有 after 约束 ? 15 : 0) + 10 + 10 + 10`。
因此未定义时序约束的规则（如 `cpu_contention`）分母为 90，评分不会因"没有时序约束"而被稀释。

- 展示为 `Evidence Match: 92/100`，**不写** `Root Cause Probability`（未做概率校准，方案 §6.3）；
- 每个根因候选都必须附 `score_breakdown`（逐维度明细）+ `evidence_ids`。

---

## 4. 诊断服务 HTTP API

默认监听 `:8010`（`rca-serve --listen :8010`），CORS 默认放开，便于 console dev server 联调。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 服务健康 + 各数据源可用性（platform / prometheus / fixture） |
| GET | `/api/v1/meta` | 规则清单、评分维度、证据信号表、端点清单 |
| GET | `/api/v1/topology` | G6 拓扑（combos + nodes + edges + 状态着色） |
| GET | `/api/v1/overview` | 健康页：汇总 + 工作负载健康卡片 + 时间线 |
| GET | `/api/v1/incidents` | 告警/事件列表（关联簇 + Top-1 诊断摘要） |
| GET | `/api/v1/incidents/{id}` | 告警详情：证据列表 + 时间线 + 诊断 + 影响范围 + 子图 |
| POST | `/api/v1/diagnose` | 对指定 `correlation_id` / `resource_id` / 时间窗执行 RCA |
| GET | `/api/v1/metrics/series` | ECharts 曲线数据（含阈值线） |
| GET | `/api/v1/rules` | 规则定义原文 + 结构（诊断页"规则可扩展"展示） |

### 4.1 `GET /api/v1/topology`

```json
{
  "generated_at": "2026-09-21T10:00:00Z",
  "source": {"platform": "real", "prometheus": "real"},
  "combos": [
    {"id": "combo:host:cbb61d8a", "label": "host-1 (GPU1)", "kind": "host", "parent": null},
    {"id": "combo:vm:63bbb461", "label": "workload-vm", "kind": "vm", "parent": "combo:host:cbb61d8a"}
  ],
  "nodes": [
    {
      "id": "vm:63bbb4613a524e4e97090600af03da93",
      "label": "workload-vm",
      "kind": "vm",
      "combo": "combo:vm:63bbb461",
      "subtitle": "10.0.0.10 · 4 vCPU / 4 GiB",
      "status": "healthy",
      "incident_count": 0,
      "badges": [],
      "metrics": [{"name": "cpu_pct", "value": 12.4, "unit": "percent"}]
    }
  ],
  "edges": [
    {"id": "e-vm-cont", "source": "vm:63bb...", "target": "container:7196bcad", "relation": "contains", "label": "contains"}
  ],
  "legend": [
    {"kind": "host", "label": "宿主机"}, {"kind": "vm", "label": "虚拟机"},
    {"kind": "container", "label": "容器"}, {"kind": "service", "label": "AI 服务"},
    {"kind": "task", "label": "Agent 任务"}, {"kind": "process", "label": "进程"}
  ]
}
```

`status ∈ healthy | warning | critical | unknown`。

### 4.2 `GET /api/v1/overview?window_seconds=900`

```json
{
  "generated_at": "2026-09-21T10:00:00Z",
  "source": {"platform": "real", "prometheus": "real"},
  "window": {"from": "2026-09-21T09:45:00Z", "to": "2026-09-21T10:00:00Z", "seconds": 900},
  "summary": {
    "resources": 14, "healthy": 11, "warning": 2, "critical": 1,
    "tasks_total": 14, "tasks_failed": 3, "incidents": 2, "open_alerts": 3
  },
  "workloads": [
    {
      "resource_id": "container:7196bcad3bc1",
      "name": "tool-service",
      "kind": "container",
      "workload_type": "tool",
      "status": "critical",
      "health_score": 38,
      "parent": {"resource_id": "vm:63bb...", "name": "workload-vm"},
      "last_event_at": "2026-09-20T08:25:40Z",
      "task_failures": 2,
      "signals": [
        {"signal": "memory.events.oom_kill", "layer": "container", "count": 4,
         "last_at": "2026-09-20T08:25:37Z", "severity": "critical"}
      ],
      "metrics": [
        {"name": "memory.current_ratio", "label": "内存使用率", "value": 1.02, "unit": "ratio",
         "status": "critical", "trend": "up"},
        {"name": "cpu.cfs.throttled_periods", "label": "CPU 限流周期", "value": 27, "unit": "count",
         "status": "warning", "trend": "flat"}
      ]
    }
  ],
  "timeline": [
    {"observed_at": "2026-09-20T08:25:37Z", "layer": "application",
     "resource_id": "task:task-1789892737-9d8d72", "resource_name": "task-1789892737-9d8d72",
     "signal": "task.failed", "severity": "major",
     "description": "tool call failed: [Errno 104] Connection reset by peer",
     "evidence_id": "ev-0007", "incident_id": "inc-d38fc66c8364"}
  ]
}
```

`health_score` 为 0–100 的展示分（由证据严重度与指标阈值综合得出，纯展示，不参与 RCA 评分）。

### 4.3 `GET /api/v1/incidents`

```json
{
  "generated_at": "2026-09-21T10:00:00Z",
  "count": 2,
  "incidents": [
    {
      "incident_id": "inc-d38fc66c8364",
      "correlation_id": "d38fc66c8364",
      "title": "容器内存耗尽（Container OOM）",
      "rule": "container_oom",
      "severity": "critical",
      "status": "open",
      "match_score": 92,
      "first_seen_at": "2026-09-20T08:25:35Z",
      "last_seen_at": "2026-09-20T08:25:37Z",
      "focus_resource": {"resource_id": "container:7196bcad3bc1", "name": "tool-service", "kind": "container"},
      "evidence_count": 9,
      "affected_tasks": 2,
      "summary": "memory.events.oom_kill Δ=4 → task.failed（同一容器，Δt=2s）",
      "source": "correlation_cluster"
    }
  ]
}
```

`source ∈ correlation_cluster（B 的关联簇） | rule_scan（C 主动扫描窗口） | fixture`。

### 4.4 `GET /api/v1/incidents/{incident_id}`

```json
{
  "incident": { "...": "同 4.3 单条" },
  "window": {"from": "...", "to": "..."},
  "diagnosis": { "...": "Top-1 Diagnosis，结构见 4.5" },
  "candidates": [ { "...": "Diagnosis" } ],
  "evidence": [ { "...": "Evidence Item，见 §1" } ],
  "timeline": [ { "...": "同 4.2 的 timeline 条目" } ],
  "impact": {
    "focus": {"resource_id": "container:7196bcad3bc1", "name": "tool-service", "kind": "container"},
    "counts": {"tasks": 2, "services": 1, "containers": 1},
    "scope": [
      {"resource_id": "task:task-1789892737-9d8d72", "kind": "task", "name": "task-1789892737-9d8d72",
       "relation": "runs_on", "depth": 1, "status": "failed"}
    ]
  },
  "graph": {"nodes": [ "同 topology.nodes" ], "edges": [ "同 topology.edges" ]}
}
```

### 4.5 `POST /api/v1/diagnose`

请求：

```json
{"correlation_id": "d38fc66c8364", "window_seconds": 900, "top_n": 3}
{"resource_id": "container:7196bcad3bc1", "from": "2026-09-20T08:21:00Z", "to": "2026-09-20T08:26:00Z"}
```

响应：

```json
{
  "window": {"from": "...", "to": "..."},
  "focus": {"correlation_id": "d38fc66c8364", "resource_id": "container:7196bcad3bc1"},
  "sources": {"platform": "real", "prometheus": "real", "evidence_count": 9},
  "diagnoses": [ { "...": "Diagnosis，按 match_score 降序" } ],
  "evidence": [ { "...": "Evidence Item" } ],
  "timeline": [ { "...": "Timeline Entry" } ],
  "impact": { "...": "同 4.4 impact" },
  "graph": {"nodes": [], "edges": []}
}
```

**Diagnosis 对象（核心，方案 §6.3 要求）**

```json
{
  "diagnosis_id": "diag-20260920T082540Z-container_oom",
  "rule": "container_oom",
  "rule_version": 1,
  "title": "容器内存耗尽（Container OOM）",
  "root_cause": "container_memory_exhausted",
  "root_cause_label": "容器 memory limit 与实际需求不匹配（或应用内存泄漏）",
  "severity": "critical",
  "match_score": 92,
  "match_note": "Evidence Match 为规则证据命中评分（0–100），非概率",
  "score_breakdown": [
    {"dimension": "rule_match", "label": "规则证据命中", "score": 55, "max": 55,
     "detail": "4/4 条命中：memory.events.oom_kill、memory.current_ratio>0.95、oom.ebpf、task.failed"},
    {"dimension": "temporal_precedence", "label": "时间优先性", "score": 15, "max": 15,
     "detail": "容器层 OOM 早于应用层 task.failed 2.0s"},
    {"dimension": "resource_adjacency", "label": "资源邻接度", "score": 10, "max": 10,
     "detail": "全部证据同属 container:7196bcad3bc1"},
    {"dimension": "signal_strength", "label": "信号强度", "score": 7, "max": 10,
     "detail": "oom_kill 增量 4，severity=critical"},
    {"dimension": "independent_evidence", "label": "独立证据数", "score": 5, "max": 10,
     "detail": "覆盖 3 类证据来源：cgroup / app_event / metric"}
  ],
  "evidence_ids": ["ev-0001", "ev-0002", "ev-0005"],
  "evidence": [ { "...": "命中的 Evidence Item" } ],
  "suggestions": [
    {"action": "adjust_memory_limit", "title": "调整容器 memory limit",
     "basis": "memory.current/max=1.02，memory.events.oom_kill Δ=4",
     "detail": "将 limit 提高到峰值 working_set 的 1.3 倍以上（当前峰值 1.46e7 字节）",
     "risk": "提高 limit 会挤占同 VM 其他容器内存，需确认 VM 余量"}
  ],
  "alternatives": [
    {"rule": "cpu_contention", "title": "CPU 资源争抢", "root_cause": "cpu_resource_contention", "match_score": 18}
  ],
  "window": {"from": "...", "to": "..."},
  "correlation_id": "d38fc66c8364"
}
```

### 4.6 `GET /api/v1/metrics/series`

```json
{
  "resource_id": "container:7196bcad3bc1",
  "window": {"from": "...", "to": "..."},
  "series": [
    {"name": "memory.current_ratio", "label": "内存使用率", "unit": "ratio",
     "points": [[1789892682, 0.42], [1789892687, 0.61]],
     "thresholds": [{"value": 0.95, "label": "memory limit", "color": "#ff4d4f"}]},
    {"name": "psi_cpu_some_avg10", "label": "CPU PSI some avg10", "unit": "percent",
     "points": [[1789892682, 0.22]], "thresholds": []}
  ]
}
```

`points` 为 `[unix_seconds, value]`。

---

## 5. Prometheus → 证据归一化映射（adapter 契约）

| 证据 signal | PromQL（adapter 内部） | 说明 |
|---|---|---|
| `memory.current_ratio` | `container_memory_working_set_bytes{name=...} / container_spec_memory_limit_bytes{name=...}` | limit 为 `max` 时该容器不计判定 |
| `memory.events.oom_kill` | `increase(container_oom_events_total{name=...}[window])` | cAdvisor 的 OOM 计数增量 |
| `container.restart` | `increase(container_start_time_seconds{name=...}[window])` 或 `changes(...)` | 重启检测 |
| `cpu.cfs.throttled_periods` | `increase(container_cpu_cfs_throttled_periods_total{name=...}[window])` | CPU 限流次数 |
| `cpu.stat.nr_throttled` | 同上（cgroup 直读时的 signal 名） | 与上者等价，两路互证 |
| `psi_cpu_some_avg10` | 来自 vm-agent 事件（Prometheus 无 PSI） | B 的 event store / fixture |
| `llama_latency_p95_ms` | 由 `inference.result` 事件的 `duration_ms` 计算 P95（窗口内） | 真实可用信号 |
| `llamacpp.tokens_per_s` | `rate(llamacpp:tokens_predicted_total[1m])` | 推理吞吐辅助证据 |

> PSI 只存在于 vm-agent 的 JSON 事件流中（Prometheus 未采集），因此 `psi_*` 类证据必须来自
> platform event store 或 fixture；这决定了 C 的两个数据源必须同时可用（见 §6）。

---

## 6. 数据源与降级（方案 §2.1 Fixture 降级要求）

C 的诊断服务以 **adapter 组合**取数，配置项 `sources`：

```json
{
  "sources": {
    "platform": {"enabled": true, "base_url": "http://127.0.0.1:8000", "token": ""},
    "prometheus": {"enabled": true, "base_url": "http://127.0.0.1:9090"},
    "fixture": {"enabled": false, "dir": "fixtures", "scenario": "case1-oom"}
  },
  "listen": ":8010",
  "console_dir": ""
}
```

- `platform` 不可用 → 只用 `prometheus` + `fixture`（证据数下降，规则匹配会给出更低分并标注缺失维度）；
- 全不可用 → `fixture` 回放（演示可复现，赛题明确要求）；
- 健康页始终展示每个来源的 `real | degraded | mock` 状态（`source` 字段），评审可一眼看出真实/回放。

---

## 7. 与其他成员的接口冻结点（W1 清单对照）

| 冻结项 | 归属 | 状态 |
|---|---|---|
| Schema v1 / 六个 Schema | 全员（B 实现） | ✅ 已冻结（方案 §5.4 + `platform/tsplatform/schema.py`） |
| Event / Evidence / Cluster HTTP API | B | ✅ 已交付（`platform/README.md`） |
| 证据 `signal` 命名 | A + B + C | ✅ 本文档 §1（与 A 的 AppEvent、vm-agent 输出对齐） |
| 规则 YAML 结构（`rule/evidence/correlation/result`） | C | ✅ 本文档 §2 |
| Evidence Match 评分维度与权重 | C | ✅ 本文档 §3 |
| 诊断服务 HTTP API（供 console） | C | ✅ 本文档 §4 |
