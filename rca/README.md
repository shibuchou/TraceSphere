# TraceSphere RCA（成员 C：诊断 / 告警 / 展示）

配置驱动的根因分析引擎 + 诊断服务 + CLI。对应方案 `方案初版.md` §6、§7 与 `开工交接-B与C.md` §4。

**边界**（方案 §6.1）：B 输出「这些事件之间有关联」（关联簇 + 结构化证据），C 输出
「最可能的问题是什么、证据是什么、影响谁、该怎么处理」。C 不重复采集、不重复关联、
不自研 Alertmanager 已有的 grouping/silence/inhibition/dedup。

```text
真实数据源                      C 侧                    输出
─────────────────────────  ─────────────────────  ─────────────────────────────
platform /api/v1/context  ─┐
platform /api/v1/clusters  ─┤
prometheus(cAdvisor)      ─┼─▶ evidence 归一化 ─▶ 规则匹配 ─▶ 根因候选 Top-N
fixtures/*.json（回放）    ─┘   （转换/去噪/合并）   Evidence    + 影响范围 + 时间线
                                                  Match 评分  + 处置建议
                                                            ↓
                                              HTTP API（:8010）+ Console + CLI
```

## 目录

```text
rca/
├── cmd/tracesphere/          CLI：serve / diagnose / topo / health / alerts / rules / capture
├── internal/
│   ├── rule/                 规则加载（YAML）+ 证据匹配 + Evidence Match 评分
│   ├── engine/               取数编排、诊断生成、影响范围、拓扑/健康/告警视图
│   ├── source/               platform / prometheus / fixture 三个适配器 + 归一化
│   ├── api/                  /api/v1/* HTTP 接口 + console 静态托管
│   ├── render/               CLI 文本渲染（CJK 宽度对齐）
│   └── model/                统一数据模型（与 docs/API.md 一一对应）
├── rules/                    三条规则：oom / cpu / tool_failure（新增 YAML 即生效）
├── fixtures/                 真实环境抓取的回放场景（tracesphere capture 产出）
├── tools/
│   ├── event-bridge.py       VM 内信号接入桥（临时，A/B 正式接入后可下线）
│   └── make_fixtures.py      从证据链报告生成 fixture（无真实环境时的备用）
└── docs/API.md               冻结契约：规则结构 / 证据模型 / HTTP API / 评分维度
```

## 快速开始

```bash
# 本地（无环境）——纯 fixture 回放
go build -o bin/tracesphere ./cmd/tracesphere
./bin/tracesphere diagnose --scenario case1-oom      # 容器 OOM
./bin/tracesphere diagnose --scenario case2-cpu      # CPU 争抢
./bin/tracesphere diagnose --scenario case3-tool-failure
./bin/tracesphere alerts --fixture --scenario case1-oom
./bin/tracesphere topo   --fixture --scenario case1-oom
./bin/tracesphere health --fixture --scenario case1-oom
./bin/tracesphere rules

# 真实环境（platform + Prometheus）
export TRACESPHERE_PLATFORM_URL=http://127.0.0.1:8000
export TRACESPHERE_PROMETHEUS_URL=http://127.0.0.1:9090
./bin/tracesphere diagnose --correlation-id <corr> --window 10m
./bin/tracesphere serve --listen :8010 --console ../console/dist   # 服务 + 前端
```

> **受限 shell（沙箱）里构建**：Go 默认把模块缓存写到用户目录，可能被拒绝。
> 此时把缓存指到工作区内即可：
> ```bash
> export GOPATH=$PWD/../.gopath GOMODCACHE=$PWD/../.gopath/pkg/mod GOCACHE=$PWD/../.gocache
> export GOFLAGS=-mod=mod GOPROXY=https://goproxy.cn,direct GOSUMDB=off
> ```
> Console 的 `npm run build` 需要能 `spawn` 子进程（Vite→esbuild），在 Windows 受限沙箱里会
> `EPERM`，请在 Linux/普通 shell 里构建（本仓库在 GPU1 上构建，见 `console/README.md`）。

一键起演示环境（platform + VM 内采集桥 + 诊断服务/Console）：

```bash
bash ../tools/demo-up.sh          # 起
bash ../tools/demo-up.sh --status
bash ../tools/demo-up.sh --stop
```

## 规则（配置驱动，方案 §6.3）

```yaml
rule: container_oom
version: 1
title: 容器内存耗尽（Container OOM）
evidence:                       # 条款权重之和即 rule_match 的分母
  - signal: memory.events.oom_kill   # 事件型证据（可 require_increase）
    kind: cgroup
    weight: 35
    require_increase: true
  - metric: memory.current_ratio     # 指标型证据（op/value 阈值）
    op: ">"
    value: 0.95
    weight: 20
  - signal: oom.ebpf                 # 可选证据：缺失不扣分
    weight: 20
    optional: true
  - signal: task.failed
    weight: 15
    after: memory.events.oom_kill    # 时序约束（Temporal Precedence 维度）
correlation:
  same_resource: true
  time_window: 5s
result:
  root_cause: container_memory_exhausted
  label: 容器 memory limit 与实际需求不匹配（或应用内存泄漏）
  suggestions:                       # 每条建议含 依据 + 操作 + 风险
    - action: adjust_memory_limit
      title: 调整容器 memory limit
      basis: ...
      detail: ...
      risk: ...
```

字段全集与语义见 `docs/API.md` §2。已交付规则：

| 规则 | 主判据 | 真实环境证据来源 |
|---|---|---|
| `container_oom` | `memory.events.oom_kill` Δ>0 | 内核 OOM 日志（`oom_memcg=docker-<id>.scope`，带容器归属） |
| `cpu_contention` | PSI `cpu.some` ↑ + `cpu.cfs.throttled_periods` Δ>0 | vm-agent PSI 事件 + cAdvisor 指标 |
| `tool_failure` | `tool.result(status=error)` + 传输层异常 | AppEvent + 错误文本/`tcp.retransmit` |

## Evidence Match 评分（0–100，**非概率**）

```text
Evidence Match = Rule Match（规则证据命中，55）
               + Temporal Precedence（时间优先性，15；规则无 after 时该维度不适用）
               + Resource Adjacency（资源图距离加权，10）
               + Signal Strength（主证据严重度 + 证据数，10）
               + Independent Evidence Count（独立证据类别数，10）
match_score = Σ得分 / Σ适用上限 × 100
```

每次诊断都输出 `score_breakdown`（逐维度 score/max/detail）与 `evidence_ids`，
**不输出** `Root Cause Probability`（未做概率校准，方案 §6.3）。

## 与上游的接口

- **B（platform）**：`/api/v1/context`、`/clusters`、`/clusters/{id}`、`/resources`、`/events`、
  `/resources/{id}/graph`、`/agents/register`。契约见 `platform/README.md`。
- **A（采集）**：AppEvent（agent-service stdout）、vm-agent JSON 事件（eBPF + PSI/cgroup）、
  容器 cgroup v2、cAdvisor/Prometheus 指标。
- **C 侧补全**：当某类证据缺失时按 `resource_id + 时间窗 + 资源图拓扑` 从 platform 补齐
  系统层证据（方案 §5.3/§5.6 的关联原则），并在 `sources.notes` 中显式说明补入了多少条。

## 测试

```bash
go test ./...            # 规则加载/评分/三场景 Top-1 回归（含真实抓取的 fixture 回放）
```

回归断言覆盖：Top-1 规则正确、评分下界、五个评分维度齐备、处置建议三段式非空、
证据 ID 可溯、影响范围与时间线非空、空证据不产出诊断。

## 数据来源标注（方案 §8）

响应中的 `source` / `sources` 字段始终标注每个来源的真实性：
`platform=real|degraded|off`、`prometheus=real|degraded|off`、`fixture=mock|off`，
证据条目带 `origin` + `mode`。Console 顶栏与页脚会显示这些状态，评审可一眼区分真实与回放。
