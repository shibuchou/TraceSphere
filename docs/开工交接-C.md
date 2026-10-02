# TraceSphere 开工交接说明（C 侧：诊断 / 告警 / 展示）

> 内部文档（含服务器地址、账号与联调细节）：**禁止放入比赛提交材料**（大赛匿名化要求）
> 维护：C ｜ 日期：2026-09-21 ｜ 前置文档：`开工交接-B与C.md`（A 维护）、`方案初版.md`（v0.4）
> 契约文档：`tracesphere/rca/docs/API.md` ｜ 验收记录：`tracesphere/docs/evidence/rca-real-run.md`

---

## 1. 交付状态

| 交付物 | 状态 | 位置 / 说明 |
|---|---|---|
| RCA Rule Engine（配置驱动，非 if/else） | ✅ 完成 | `rca/internal/rule/`：YAML 加载 + 证据匹配 + Evidence Match 评分 |
| 三条规则 `oom` / `cpu_contention` / `tool_failure` | ✅ 完成 | `rca/rules/*.yaml`，实测 Top-1 命中（见 §4） |
| Evidence Match 五维度评分 + 明细 | ✅ 完成 | `rule_match / temporal_precedence / resource_adjacency / signal_strength / independent_evidence` |
| 影响范围（受影响 AgentTask / 服务 / 容器） | ✅ 完成 | 沿资源图 BFS + 失败任务反查，输出 `impact.scope` |
| 处置建议（依据 + 操作 + 风险三段式） | ✅ 完成 | 规则 `result.suggestions` 驱动 |
| 诊断服务 HTTP API（供 Console/CLI） | ✅ 完成 | `rca/internal/api/`，9 个端点，契约 `rca/docs/API.md` §4 |
| CLI `tracesphere` | ✅ 完成 | `serve / diagnose / topo / health / alerts / rules / capture` |
| Web Console 四视图 | ✅ 完成 | `console/`：React+TS+AntD+G6 v5+ECharts；GPU1 上 `tsc` 零错误、`vite build` 成功（3.5 MB dist） |
| Fixture 降级/回放 | ✅ 完成 | 三个场景由**真实环境抓取**（`tracesphere capture`），`--scenario` 一键回放 |
| 真实环境三场景端到端 | ✅ 完成 | Case1 OOM 75/100、Case2 CPU 97/100、Case3 工具失败 93/100（Top-1 全部正确） |
| 一键起演示环境 | ✅ 完成 | `tools/demo-up.sh`（platform + VM 采集桥 + 诊断服务/Console） |
| 告警运营（Alertmanager 对接） | ⏳ 未做 | P1；本侧只做告警**视图**与分级展示，不自研 grouping/silence/inhibition/dedup |
| 演示视频（赛题 g） | ⏳ 待录 | 建议按 §9 的脚本录 3–5 分钟 |

**结论**：C 侧全部 P0 交付物完成并通过真实环境验收；剩余为 P1（Alertmanager 联动）与录屏。

---

## 2. 代码位置

```text
tracesphere/
├── rca/                       ← C 侧核心（Go，无第三方依赖除 gopkg.in/yaml.v3）
│   ├── cmd/tracesphere/       CLI 入口
│   ├── internal/{rule,engine,source,api,render,model}/
│   ├── rules/                 三条规则 YAML（新增 YAML 即生效）
│   ├── fixtures/              真实抓取的回放场景（case1-oom / case2-cpu / case3-tool-failure）
│   ├── tools/event-bridge.py  VM 内信号接入桥（**临时**，见 §6）
│   ├── tools/make_fixtures.py 无环境时从证据链报告生成 fixture（备用）
│   └── docs/API.md            ★ 冻结契约（规则结构 / 证据模型 / HTTP API / 评分维度）
├── console/                   ← C 侧前端（React + TS + AntD + G6 v5 + ECharts）
│   ├── src/{pages,components,data,mocks}/   四页面 + 数据源适配 + 回放数据
│   └── scripts/check-*.mjs    夹具/契约自检（73 断言）+ CSS Module 自检
├── tools/demo-up.sh           ← 一键起演示环境（C 新增）
└── docs/evidence/             A 的证据链报告 + C 的真实验收记录
```

构建/运行环境：
- GPU1 无系统 Node，已装独立 Node 22 工具链：`~/opt/node-v22.14.0-linux-x64/bin`（构建 console 时必须先 `export PATH`）
- Go：GPU1 自带 go1.22.2；GOFLAGS=-mod=mod，yaml.v3 已在模块缓存中
- 诊断服务端口 **8010**（B 的 platform 占 8000，VM 内 Prometheus 9090 / cAdvisor 8080 / llama 8081 / agent-service 8082）

---

## 3. 快速上手

### 3.1 一键起（GPU1 上）

```bash
bash ~/tracesphere/tools/demo-up.sh            # platform + VM 采集桥 + 诊断服务/Console
bash ~/tracesphere/tools/demo-up.sh --status   # 状态（含 platform/rca/bridge 进程与数据源健康）
bash ~/tracesphere/tools/demo-up.sh --stop
# 浏览器打开 http://<GPU1-IP>:8010/  （Console 由诊断服务静态托管，API 同源，无 CORS）
```

### 3.2 常用 CLI

```bash
cd ~/tracesphere/rca
./bin/tracesphere alerts  --window 10m                     # 告警/事件列表（关联簇 + Top-1 摘要）
./bin/tracesphere health  --window 15m                     # 工作负载健康 + 时间线
./bin/tracesphere topo    --focus container:<id>           # 资源拓扑（Host→VM→Container→Service→Task）
./bin/tracesphere diagnose --correlation-id <corr> --window 10m     # 指定 Agent 任务做 RCA
./bin/tracesphere diagnose --resource-id container:<id> --json      # 原始结构（脚本/取证）
./bin/tracesphere rules                                    # 规则库
./bin/tracesphere capture --scenario caseN --correlation-id <corr> --window 10m --out fixtures
# 无环境时的回放
./bin/tracesphere diagnose --scenario case1-oom
```

### 3.3 Console

```bash
cd ~/tracesphere/console
export PATH=$HOME/opt/node-v22.14.0-linux-x64/bin:$PATH
npm ci && npm run build          # 产出 dist/，由诊断服务托管
npm run dev -- --host 0.0.0.0    # 开发模式（vite proxy 转发 /api/v1 → 127.0.0.1:8010）
# 数据源切换：VITE_DATA_SOURCE=api（默认）| fixture（读 src/mocks/*.json，无需后端）
```

### 3.4 重新构建

```bash
cd ~/tracesphere/rca && GOFLAGS=-mod=mod go build -o bin/tracesphere ./cmd/tracesphere && go test ./...
cd ~/tracesphere/console && npm run build
```

---

## 4. 真实环境联调结果（2026-09-21）

链路：**真实注入 → VM 内真实采集 → platform 入库/关联 → C 侧 RCA → Console**。

```text
A: docker update/toxiproxy/cpu-stress   （VM 10.100.0.181）
        │
        ├─ agent-service stdout: AppEvent（task.*/tool.*/inference.*，带 correlation_id）
        ├─ vm-agent stdout: eBPF 事件（exec/exit/oom/retransmit）+ PSI/cgroup 指标（5s）
        ├─ 容器 cgroup v2: memory.current/max、memory.events.oom_kill、cpu.stat
        └─ 内核日志: oom-kill（oom_memcg=docker-<id>.scope，**带容器归属**）
        ▼
event-bridge.py（VM 内，10s 轮询，归一化 + dedup_key）→ POST /api/v1/events
        ▼
B: platform（用 SQLite WAL 落库 → /correlate 生成关联簇 + 证据）
        ▼
C: 诊断服务（platform /context + Prometheus + 拓扑补全 → 规则匹配 → 诊断）
        ▼
Console 四视图 / CLI
```

| Case | 注入 | 实测证据 | Top-1 | 评分 |
|---|---|---|---|---|
| 1 容器 OOM | `docker update --memory=8m tool-service` | 内核 OOM 8 次 + 容器重启 Δ=8 + `task.failed` | 容器内存耗尽（Container OOM） | 75/100 |
| 2 CPU 争抢 | `cpu-stress`(2w) + `docker update --cpus=0.5 llama-server` | PSI `cpu.some` 峰值 40.9% + `cpu.cfs.throttled_periods` Δ=1190 + 推理 `timed out` | CPU 资源争抢 | 97/100 |
| 3 工具失败 | Toxiproxy 关停 tool proxy | `tool.result` error（Connection refused）+ `task.failed` + `tcp.retransmit` | Agent 工具调用失败 | 93/100 |

平台侧规模（Case 3 结束时）：`resources 33 / edges 32 / events 239 / evidence 239 / clusters 14 / agents 1`。
完整输出见 `tracesphere/docs/evidence/rca-real-run.md`。

> **复跑即可复现**：`bash tools/acceptance.sh` 会依次跑完三个场景（每个场景重置 DB → 持续采集 →
> 注入 → 触发任务 → 恢复 → 关联 → RCA → 抓取真实 fixture），报告落在 `/tmp/final/case*.txt`。

> Case 1 未满分的原因写在评分明细里（本轮 `task.failed` 早于 OOM 152s，时序维度判 0），
> 这是"证据驱动、可解释"的正常表现，不是缺陷。

---

## 5. 接口与契约（W1 冻结项）

| 冻结项 | 状态 | 位置 |
|---|---|---|
| Schema v1（六个 Schema） | ✅ 沿用 B 的实现 | `platform/tsplatform/schema.py` + 方案 §5.4 |
| 证据 `signal` 命名表 | ✅ 冻结 | `rca/docs/API.md` §1 |
| 规则 YAML 结构（`rule/evidence/correlation/result`） | ✅ 冻结 | `rca/docs/API.md` §2 + `rca/rules/*.yaml` |
| Evidence Match 五维度与权重 | ✅ 冻结 | `rca/docs/API.md` §3（引擎实现 `rca/internal/rule/score.go`） |
| 诊断服务 HTTP API（Console 契约） | ✅ 冻结 | `rca/docs/API.md` §4 |
| Prometheus → 证据归一化映射 | ✅ 冻结 | `rca/docs/API.md` §5 |
| 数据源降级优先级（real → degraded → fixture） | ✅ 冻结 | `rca/docs/API.md` §6，实现于 `rca/internal/engine/engine.go` |

**契约歧义已定**：`GET /api/v1/overview` **接受** `window_seconds`（默认 900），
`/topology`、`/incidents`、`/metrics/series` 同理；Console 已按带参实现。

---

## 6. 联调中发现的接口缺口（**给 A / B 的明确待办**）

这几条是本轮真实联调暴露出来的、跨成员的问题。C 侧都做了兜底，但**正式版本应由归属方修正**，
否则会持续以"临时桥 + C 侧推断"的形式存在。

### 6.1 给 B（platform）

1. **container 资源没有 `vm_id`**：事件惰性创建容器时只写 `name = container_id[:12]`，不写 `vm_id`
   → 资源图缺 `VM → Container` 边，拓扑树断裂。
   - C 侧兜底：`source.EnrichEdges`（单 VM 环境按 Agent Registration 推断，边标 `origin=platform-inferred`）
   - 建议：`ingest._lazy_get` 支持从 `payload.attributes.vm_uuid` 落到 `vm_id`；或提供通用资源/边写入接口。
2. **容器名是哈希占位**：`name = container_id[:12]`，UI 节点显示哈希。
   - C 侧兜底：`PrometheusClient.resolveContainer` 用 cAdvisor 的 `id` 标签反查真实 docker name 回填。
   - 建议：`container.discovered` 事件里的 `attributes.name` 落到资源 `name`。
3. **事件的 `payload.value` / `payload.delta` 未进入证据**：C 原先拿不到 OOM 增量数值。
   - C 侧已适配（读 `payload.value|delta`）。建议 platform 的 evidence 原生带 `value` / `unit`。
4. **`/api/v1/context` 返回的 `window.seconds` 为 0**：C 目前按 `from/to` 自算，建议补齐字段。
5. **关联簇时间窗固定 ±5s**：OOM 与 `task.failed` 之间可能间隔数十秒到数分钟（本轮 152s），
   系统层信号因此不在簇内。
   - C 侧兜底：`engine.widenSystemEvidence`（按"同一 VM 子树 + 时间窗"补入系统层证据，并在 `sources.notes` 说明条数）。
   - 建议 W2 在 B 的关联引擎里支持可配置时间窗 + Evidence Snapshot（方案 §5.5 W2 计划）。

### 6.2 给 A（vm-agent / 负载 / 注入）

1. **vm-agent 与 agent-service 都没有 HTTP 上报**：只打 stdout / docker logs，
   而 platform 只提供 `POST /api/v1/events` 入库。
   - C 侧兜底：`rca/tools/event-bridge.py`（VM 内运行，**临时**；A/B 正式接入后直接下线）。
   - 建议：vm-agent 按 `POST /api/v1/events` 直报（方案 §3.2），AppEvent 增加 `container_id`
     （否则任务事件无法归属到容器）。
2. **vm-agent 松散事件用 `kind`（1..4）区分子类型**，platform 需要 `event_type`。
   - 桥内已做映射：`1/2 → process.exec/process.exit`、`3 → oom.ebpf`、`4 → tcp.retransmit`。
   - 建议：vm-agent 直接输出 `event_type`，与 `rca/docs/API.md` §1 的信号表对齐。
3. **★ 本环境 cAdvisor 的 `container_oom_events_total` 恒为 0**（cAdvisor v0.49.1 在该内核上不计数），
   且容器重启后自身 cgroup 的 `memory.events.oom_kill` 归零 → **Case1 的"必需证据"取不到**。
   - 现行方案：从**内核日志**取（`journalctl -k`，`oom-kill: … oom_memcg=/system.slice/docker-<id>.scope`），
     该记录同时提供容器归属 + 精确时间 + 被杀进程，是唯一权威来源；桥已实现解析。
   - 建议 A 把这一路采集做进 vm-agent（或保留 cgroup 轮询 + `RestartCount` 差分作为补充证据）。
4. **`docker update --memory=8m` 偶发 runc 报错**（容器重启中改 cgroup 失败）。
   - 注入脚本应改为"重试 + 探活直到工具真的不可用"（`tools/case1-oom-real.sh` 已按此实现，可参考）。
5. **PSI 只在 vm-agent 事件流里**（Prometheus 未采集 PSI），Case2 的 PSI 证据依赖平台事件；
   若 A 在 Prometheus 侧也暴露 PSI，规则可少一路依赖。

### 6.3 给 C（后续自己）

- Console 的 fixture 模式 mocks 仍是手工数据；可用 `tracesphere capture` 产物一键替换（脚本待补）。
- Alertmanager 联动（分级/静默/抑制/去重落到告警页）未做（P1）。
- 诊断历史（`/api/v1/diagnoses` 最近 N 条）未做，Console 每次现算；数据量大时可加缓存。

---

## 7. 已知问题与风险

1. **容器身份抖动**：`docker compose up --force-recreate` 会换 container_id；
   历史 OOM 证据会挂到旧容器资源上。演示前建议 `reset-platform.sh` 重置 DB（见 §9），
   或让 bridge 用较小的 `--oom-minutes`（默认 5）避免把历史 OOM 重新灌入当前诊断。
2. **C 侧拓扑推断边**：单 VM 环境下的 `VM → Container` 边是推断的（标记 `platform-inferred`），
   换到多 VM 环境前必须先修 B 的 `vm_id`（§6.1-1），否则会挂错 VM。
3. **Prometheus 容器选择器**：本环境 cAdvisor 没有 `name` 标签，C 用 `id=~".*<container_id[:12]>.*"`；
   若换 cAdvisor 版本需回归。
4. **事件量**：vm-agent 的进程 exec/exit 事件量极大，桥默认**不上报**（`--include-process` 可开）；
   诊断侧 `source.Condense` 会把计数型证据合并（窗口增量合计）、指标型取峰值、丢弃
   `container.discovered` / `process.*` / 原始 `cgroup.metric` 噪声行。
5. **Console 构建环境**：本机（Windows）沙箱禁止 esbuild `spawn`+pipe，`npm run build` 会 `EPERM`；
   必须在 GPU1（Linux + Node 22）构建，命令见 §3.3。
6. **时钟**：管理节点曾发生时间跳变；关联时间窗依赖时钟一致性，演示前建议跑一次
   `platform/tools/capture_fixtures.py` 自带的 skew 检查。

---

## 8. 下一步建议（对齐方案 §10.2 W2/W3）

| 优先级 | 事项 | 归属 |
|---|---|---|
| P0 | B 侧修 `vm_id` / 容器真实名 / evidence `value`，落地 §6.1 的 4 条 | B |
| P0 | A 侧把 vm-agent + AppEvent 直报 `/api/v1/events`（替换临时桥），并补 `container_id` | A |
| P0 | Case2 加强注入（cpu.max 收紧 + 并发）复现"任务超时"，把 `task.failed(timeout)` 纳入 Case2 固定验收 | A + C |
| P1 | Alertmanager 接入告警页（分级颜色、静默、抑制来源展示） | C |
| P1 | Console fixture mocks 用真实 capture 产物替换；`/api/v1/diagnoses` 历史缓存 | C |
| P1 | 探针开销测量与卸载说明补进文档 n（A 侧已有 `measure-overhead.sh`） | A |
| P2 | Evidence Snapshot 快照持久化 + 复杂历史 RCA | B + C |

---

## 9. 演示脚本（录屏建议，赛题 g）

```bash
# 0) 起环境（干净基线）
bash ~/tracesphere/tools/demo-up.sh
bash ~/tracesphere/tools/reset-platform.sh                 # 可选：清空历史事件，基线更干净

# 1) 打开 Console：拓扑页（Host→VM→Container→Service→Task 五层）→ 健康页（基线全绿）
# 2) Case1 容器 OOM：注入 → 健康页变红 → 告警列表出现"容器内存耗尽" → 诊断页看 Evidence Match 明细
sudo bash ~/tracesphere/tools/case1-oom-real.sh /tmp/demo-cases 8m   # 需先拷到 VM 上执行（见下）
# 3) Case2 CPU 争抢：cpu-stress + 收紧 llama cpu.max → 推理超时 → CPU 争抢 Top-1
# 4) Case3 工具失败：Toxiproxy 关停 tool → 连接被拒 → 工具调用失败 Top-1
# 5) 降级演示：断掉 platform（或换台机器）
bash ~/tracesphere/rca/bin/tracesphere serve --fixture --scenario case1-oom --console ~/tracesphere/console/dist
```

> 三个 `caseN-*-real.sh` 脚本在 **workload-vm 内**执行（需要 docker 权限），从 GPU1 执行：
> `sshpass -p <password> scp tools/case*.sh ubuntu@10.100.0.181:/tmp/` 后
> `sshpass -p <password> ssh ubuntu@10.100.0.181 'sudo bash /tmp/case1-oom-real.sh'`。
> 每个脚本最后一行输出 `CORR=<correlation_id>`，用它跑
> `tracesphere diagnose --correlation-id <CORR> --window 10m`。

录屏要点：① 顶部数据源角标 `API LIVE` 证明是真实数据；② 诊断页强调
`Evidence Match: N/100` 与"证据命中评分，非概率"；③ 每条结论都能点开证据 ID 溯源；
④ 最后切 fixture 回放展示可复现性。

---

## 10. 注意事项

1. **匿名化**：所有提交材料不得出现学校、指导教师等信息；本文件含凭据与内网地址，仅内部使用。
2. **凭证**：ZSvirt 密码只走环境变量（`ZSVIRT_PASSWORD`），Bridge 不含任何明文口令；
   本文件与 `deploy/README.md` 属于内部资料，交付前务必剔除。
3. **资源纪律**：GPU1 为共享实验机；演示用的故障注入容器（`cpu-stress` / `oom-victim`）用完请清理：
   `sudo docker rm -f cpu-stress oom-victim`；`docker update` 施加的 limit 用
   `docker compose up -d --force-recreate <svc>` 还原。
4. **每日开工自检**：`demo-up.sh --status` → `tracesphere health` → `tracesphere alerts`，
   三者都应为 `real` 且有数据。
