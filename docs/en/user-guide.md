# TraceSphere User Guide

> A full-stack observability platform for containers and agent workloads inside ZSvirt virtual machines
> Shanghai Open Source Software Application Innovation Competition (上海开源软件应用创新大赛) · Based on the ZSvirt virtualization platform
> Document version: v1.0 (2026-10-27) | Applies to: TraceSphere v0.1

[中文](../用户手册.md) | English

---

## 1. About This Document

### 1.1 Intended Readers

| Reader | Focus |
|---|---|
| SRE / platform operations | Topology, health, incidents, evidence chain, remediation suggestions |
| Agent / application developers | Task failure causes, tool call errors, inference anomalies |
| Evaluation / demo staff | Data source markers, demo paths, four-scenario switching |
| Automation script authors | CLI, HTTP API, fixture replay |

### 1.2 What You Get

TraceSphere answers one question:

> **For a single failed Agent task, was the cause the application, the container, the virtual machine, the GPU, or the host?**

It puts ZSvirt resources, in-VM system signals, Prometheus metrics, and Agent application events into a single evidence chain, and produces:

- Root cause candidates Top-N (ranked by Evidence Match);
- A five-dimension score breakdown for each candidate;
- Evidence IDs that can be traced one by one;
- Affected resources and tasks;
- Remediation suggestions with "basis / action / risk" (依据 / 操作 / 风险).

### 1.3 Related Documents

| Document | Purpose |
|---|---|
| [README](../../README.en.md) | Project overview and quick start |
| [Deployment guide (部署文档)](deployment-guide.md) | Deploy from scratch |
| [Testing guide (测试文档)](testing-guide.md) | Test results and evidence boundaries |
| [Solution overview (方案说明)](solution-overview.md) | Architecture and design |
| [RCA API contract (RCA 接口契约)](../../rca/docs/API.md) | API fields and scoring definitions |

---

## 2. Access and Sign-in

### 2.1 Opening the Console

After deployment, open:

```text
http://<PLATFORM_IP>:8010/
```

The default route redirects to `/health`, the Health overview (健康总览).

### 2.2 Authentication

The Console has no username / password system; it supports only a static token:

- If `TRACESPHERE_RCA_TOKEN` was not set during deployment, simply open the URL;
- If a token is set, use the following for the first access:

```text
http://<PLATFORM_IP>:8010/?token=<RCA_TOKEN>
```

The page writes the token into the browser's `localStorage` under `tracesphere.auth_token`, and subsequent requests automatically carry `Authorization: Bearer`. The token stays in the address bar, so before a demo it is advisable to reopen the address without `?token=`.

When the token expires or is cleared, the page shows a 401 error; reopen it with `?token=`.

### 2.3 Browser and Network

- Latest Chrome / Edge is recommended;
- The Console must reach same-origin `/api/v1`; if the Console is served by RCA, usually no extra configuration is needed;
- If accessed through Nginx / a gateway, `/api/v1` must be reverse-proxied to port 8010 of RCA;
- All page times are shown in UTC, consistent with ZSvirt / platform logs.

---

## 3. Interface Overview

### 3.1 Top Bar (顶栏)

```text
TraceSphere RCA Console | 01 Topology (拓扑) | 02 Health (健康) | 03 Incidents (告警) | 04 Diagnosis (诊断) | Environment label (环境标识) | Data source badge (数据源徽标) | Data source switch (数据源切换)
```

| Element | Description |
|---|---|
| `01 Topology (拓扑)` | Resource topology |
| `02 Health (健康)` | Health overview (default page) |
| `03 Incidents (告警)` | Incident list; shows a numeric badge when there are open (未处理) incidents |
| `04 Diagnosis (诊断)` | Root cause diagnosis |
| Environment label (环境标识) | Configured via `VITE_ENV_LABEL`, e.g. "ZSvirt AI Computing Cloud · Demo Environment" (ZSvirt 智算云 · 演示环境) |
| Data source badge (数据源徽标) | `API LIVE` / `FIXTURE REPLAY`; hover to see the request base URL and the switch command |
| Data source switch (数据源切换) | Pops up a build-time variable explanation; switching requires restarting the dev server or rebuilding |

### 3.2 Demo Path Bar (演示路径条)

Below the top bar is the demo control bar:

| Element | Description |
|---|---|
| Demo path (演示路径) | Four scenario buttons: Container OOM (容器 OOM), CPU contention (CPU 争抢), Tool failure (工具失败), GPU memory exhaustion (GPU 显存耗尽) |
| Current scenario (当前场景) | Shows the `correlation_id`, rule ID, and a scenario hint |
| Refresh (刷新) | Fetch data immediately |
| Auto 20s (自动 20s) | Refresh automatically every 20 seconds |

Switching a scenario will:

- write `scenario`, `correlation_id`, or `resource_id` into the URL;
- focus the topology page on that scenario's focus resource;
- auto-fill `correlation_id` on the diagnosis page and run it;
- add a "current scenario" (当前场景) marker to the corresponding incident on the incidents page.

### 3.3 Footer (页脚)

The footer shows:

- Last data fetch time (UTC);
- API base URL;
- Source status bar: `platform: 真实 / prometheus: 真实 / fixture: 回放` (real / real / replay);
- Version and competition markers.

The source status bar is the first place to check whether data is real or replayed.

### 3.4 Colors and Labels

| Category | Values | Meaning |
|---|---|---|
| Health status (健康状态) | Healthy / Warning / Critical / Unknown (健康 / 警告 / 严重 / 未知) | Resource and workload status |
| Evidence severity (证据严重度) | Info / Warning / Major / Critical (提示 / 警告 / 重要 / 严重) | `info / warning / major / critical` |
| Evidence layer (证据层级) | Application / Container / VM / Cloud platform (应用层 / 容器层 / 虚拟机层 / 云平台层) | `application / container / vm / zsvirt` |
| Incident status (告警状态) | Open / Acknowledged / Resolved / Silenced (未处理 / 已确认 / 已恢复 / 已静默) | `open / acknowledged / resolved / silenced` |
| Source kind (来源类别) | cgroup v2 / eBPF / Metric / App event / Log / ZSvirt / Topology (cgroup v2 / eBPF / 指标 / 应用事件 / 日志 / ZSvirt / 拓扑) | Where the evidence came from |

Status colors express health semantics only: green = Healthy (健康), orange = Warning (警告), red = Critical (严重), gray = Unknown (未知). Layer colors are used on the timeline: application blue, container cyan, VM purple, cloud platform brown.

---

## 4. Core Concepts

### 4.1 Resource Identifiers

Format: `<kind>:<key>`.

| Example | Meaning |
|---|---|
| `host:<uuid>` | Host |
| `vm:<uuid>` | Virtual machine |
| `container:<64-char id>` | Container |
| `service:<name>` | AI service |
| `task:<task_id>` | Agent task |
| `process:<pid>:<start_time>` | Process |
| `gpu:<uuid>` | GPU (in mock mode, `gpu:mock-gpu0`) |

### 4.2 correlation_id

The application-level correlation anchor for a single Agent task. agent-service generates a 12-character ID for each `/task`, and every `task.started / tool.call / tool.result / inference.result / task.failed / task.finished` inside the task carries the same `correlation_id`.

Usage:

- Enter a `correlation_id` on the diagnosis page to see all evidence related to that task;
- Search the incident list for a `correlation_id` to locate the corresponding incident;
- Pass `?correlation_id=...` directly in the URL.

### 4.3 Evidence (证据)

Evidence is a structured fact that the platform normalizes from raw events. Key fields:

| Field | Description |
|---|---|
| `evidence_id` | Evidence ID; can be cited individually |
| `signal` | Normalized signal name, e.g. `memory.events.oom_kill` |
| `kind` | cgroup / ebpf / metric / app_event / log / zsvirt / topology |
| `layer` | application / container / vm / zsvirt |
| `resource_id` / `resource_name` | The resource the evidence belongs to |
| `observed_at` | Observation time (UTC) |
| `severity` | info / warning / major / critical |
| `description` | Human-readable description |
| `value` / `unit` | Numeric value and unit |
| `source_event_ids` | Raw event IDs; traceable back to the source |
| `mode` | real / mock |

### 4.4 Incident (告警)

One correlation cluster + a Top-1 diagnosis summary = one incident. An incident is not "a single metric crossing a threshold" but "multiple cross-layer evidence items judged to be the same fault".

Incident states:

```text
open (未处理) → acknowledged (已确认) → resolved (已恢复)
       ↘ silenced (静默) ↗
```

State is written to a JSON file in RCA and survives restarts; it does not depend on an external Alertmanager.

### 4.5 Evidence Match

A rule-evidence hit score, 0–100, **not a probability and not an accuracy rate**. Five dimensions:

| Dimension | Max | Meaning |
|---|---:|---|
| Rule evidence hit (规则证据命中) | 55 | How many YAML clauses were hit |
| Temporal precedence (时间优先性) | 15 | Whether the root cause signal precedes the business failure; when a rule has no `after`, this dimension does not apply |
| Resource adjacency (资源邻接度) | 10 | Whether the evidence is on the same resource / same VM / graph-adjacent |
| Signal strength (信号强度) | 10 | Severity of the main evidence and the number of extra evidence items |
| Independent evidence count (独立证据数) | 10 | How many kinds of evidence sources are covered |

The total is normalized by the "sum of applicable dimension maxima". When a rule has no temporal constraint, the denominator is 85 instead of 100, so the sub-scores may not appear to add up to the total; this is by design.

### 4.6 health_score

A 0–100 display score on the workload cards of the Health page, derived from evidence severity and metric thresholds. It is used only for sorting and display and **does not participate in RCA scoring**.

---

## 5. Resource Topology

Route: `/topology`

### 5.1 Purpose

See "who carries whom" through ZSvirt's five-layer resource relationships:

```text
Host (宿主机) → VM (虚拟机) → Container (容器) → Service (服务) → Agent task (Agent 任务)
```

GPU degraded mode additionally shows:

```text
Host (宿主机) → GPU → VM (虚拟机)
```

### 5.2 Top Summary

| Card | Meaning |
|---|---|
| Total resources (资源总数) | Total number of topology nodes |
| Healthy / Warning / Critical / Unknown (健康 / 警告 / 严重 / 未知) | Number of resources in each state |
| Related incidents (关联告警) | Total incidents and open count |

### 5.3 Canvas Operations

| Action | Method |
|---|---|
| Pan (平移) | Drag the canvas |
| Zoom (缩放) | Mouse wheel, or the `+` / `-` at the bottom right |
| Fit to canvas (适应画布) | The "Fit to canvas" (适应画布) button at the bottom right |
| View details (查看详情) | Click a node to open the drawer on the right |
| Focus a resource (聚焦资源) | The "Focus a resource" (聚焦某资源) dropdown at the top; searchable |
| Switch level (切换层级) | `L1 Cloud platform (云平台)` / `L2 Workloads (工作负载)` / `L3 Processes (进程)` |
| Filter by resource kind (资源种类过滤) | Toolbar dropdown; filter by host / VM / container / service / task / GPU |

Levels:

- **L1 Cloud platform (云平台)**: shows only the skeleton such as hosts and VMs;
- **L2 Workloads (工作负载)**: expands containers, services, and tasks;
- **L3 Processes (进程)**: adds the process layer; has content only when `process` nodes have been collected.

### 5.4 Node Drawer (节点)

After clicking a node, it shows:

- Status, resource ID, name, subtitle (e.g. IP, specs);
- Workload health score, failed task count, latest event time;
- Metrics (e.g. CPU, memory, throttling);
- Related events (current time window);
- Related incidents;
- Adjacent resources, which can be clicked to navigate further.

### 5.5 Sidebar (侧栏)

| Block | Purpose |
|---|---|
| Incident resources (告警资源) | Resources that currently have incidents; click to focus |
| Recent events (最近事件) | The latest 8 events within a 15-minute window |
| Demo tips (演示提示) | Scenario switching and level explanations |

### 5.6 Empty State

If the current real data does not contain the focus resource of the demo scenario, the page shows a hint that "the topology will not pretend to be focused" (拓扑不会假装已聚焦). This is not an error but a mismatch between the data source and the scenario; switch to a fixture build or pick a resource that actually exists.

---

## 6. Health Overview

Route: `/health` (default page)

### 6.1 Purpose

Start with the conclusions: how many resources are unhealthy, how many tasks failed, which workload is degrading, and when and at which layer events happened.

### 6.2 Top Summary Cards

| Card | Meaning |
|---|---|
| Total resources (资源总数) | Total topology nodes, including hosts / VMs / containers / services / tasks |
| Healthy / Warning / Critical (健康 / 警告 / 严重) | Resource count and percentage for each state |
| Total tasks (任务总数) | Number of agent-service tasks in the window |
| Failed tasks (任务失败) | Failed task count and percentage |
| Incidents (告警数) | Total incidents and open count |

### 6.3 Toolbar

| Control | Options | Description |
|---|---|---|
| Time window (时间窗) | 15 minutes / 1 hour / 6 hours | Affects the summary, workloads, and timeline |
| Workload filter (工作负载过滤) | All / Containers only / Services only (全部 / 仅容器 / 仅服务) | Affects workload cards only |
| Sort (排序) | By status severity / By health score ascending / By failed task count / By name (按状态严重度 / 按健康分升序 / 按任务失败数 / 按名称) | Default: by status severity |
| Refresh (刷新) | Fetch data immediately | Equivalent to the top bar refresh |

### 6.4 Workload Cards

Each card shows:

- Name, `resource_id`, type (container / service / vm);
- `health_score` and the status label;
- Parent resource link (e.g. the owning VM);
- Up to 4 key metrics: value, threshold, trend arrow (↑ / ↓ / →), and progress bar;
- Anomaly signal list: signal, layer, count, latest time;
- Failed task count, latest event time;
- Actions: containers show "Diagnose" (诊断); all resources show "Topology" (拓扑);
- The current scenario focus is marked "Current scenario focus" (当前场景焦点);
- When there are failed tasks, a hint suggests "view incident details to locate the evidence chain" (建议查看告警详情定位证据链).

### 6.5 Global Event Timeline

- Colored by layer: cloud platform → VM → container → application;
- Multi-layer events at the same moment are merged into one entry;
- Layer toggles are available at the top;
- Used to read the causal order "system-layer signals first, application-layer symptoms after".

### 6.6 Empty State

When there are no events in the time window, the page suggests switching to a larger window or checking whether the platform / vm-agent data sources are available.

---

## 7. Incident List

Route: `/incidents`

### 7.1 Purpose

View all correlation clusters and their Top-1 diagnosis summaries; filter and sort by severity, score, and time.

### 7.2 Summary Cards

| Card | Meaning |
|---|---|
| Total incidents (告警总数) | Current list total |
| Critical / Major (严重 / 重要) | Counts by severity |
| Open (未处理) | Number of incidents in `open` state |
| Affected tasks (受影响任务) | Sum across incidents (before de-duplication) |

### 7.3 Filters and Search

| Control | Description |
|---|---|
| Keyword (关键字) | Search `incident_id` / `correlation_id` / title |
| Status (状态) | All statuses / Open only (全部状态 / 仅未处理) |
| Severity (严重度) | Multi-select: Critical / Major / Warning / Info (严重 / 重要 / 警告 / 提示) |
| Rule (规则) | Filter by rule ID; shows the count for each rule |
| Time window (时间窗) | Last 15 minutes / 1 hour / 6 hours / 24 hours; filters by `last_seen_at` |
| Resource filter (资源筛选) | Appears when you arrive with a `resource_id` from the topology or diagnosis page; can be cleared in one click |
| Refresh (刷新) | Fetch data immediately |

### 7.4 Table Columns

| Column | Description |
|---|---|
| Severity (严重度) | Incident severity |
| Rule / Title (规则 / 标题) | Title, rule ID, `incident_id`, `correlation_id`, summary; marked when it is the current scenario |
| Key resource (重点资源) | Resource name and `resource_id` |
| Evidence Match | 0–100 with a progress bar; red at ≥80, orange at ≥55 |
| Affected tasks (影响任务) | Affected task count / evidence count |
| First / Latest (首次 / 最近) | First and latest occurrence times |
| Status (状态) | Open / Acknowledged / Resolved / Silenced (未处理 / 已确认 / 已恢复 / 已静默), plus the source |
| Actions (操作) | "Details" (详情) |

Click the title or "Details" (详情) to open the incident details.

---

## 8. Incident Details

Route: `/incidents/:id`

### 8.1 Page Layout

Organized as "facts → diagnosis → evidence → remediation → impact":

1. Header: title, summary, severity, status, rule, `correlation_id`, time window, source status;
2. Action buttons: Silence / Unsilence (静默 / 取消静默), Acknowledge (确认), Mark resolved (标记已处理), Back to list (返回列表), Re-run diagnosis (重新诊断), View in topology (在拓扑中查看);
3. Summary cards: evidence count, affected tasks, Top-1 score, candidate count, first seen, latest update;
4. Event summary: Top-1 diagnosis + five-dimension score breakdown + key resource / root cause / source / time window / severity;
5. Evidence list: evidence that hit Top-1 is marked with ★, and the raw payload can be expanded;
6. Remediation suggestions: each contains basis / action / risk (依据 / 操作 / 风险);
7. Layered timeline;
8. Impact scope: affected tasks, services, containers; `depth` is the distance in the resource graph;
9. Alternative candidates: Top-N ranking semantics; click to switch the view (shown when the candidate count > 1);
10. Related resource subgraph: zoomable, fit-to-canvas;
11. Metric charts: provided only for container-type focus resources; include threshold lines.

### 8.2 State Actions

| Current state | Available actions | Result |
|---|---|---|
| Open (未处理) | Silence, Acknowledge, Mark resolved (静默 / 确认 / 标记已处理) | `silenced` / `acknowledged` / `resolved` |
| Acknowledged (已确认) | Silence, Mark resolved (静默 / 标记已处理) | `silenced` / `resolved` |
| Silenced (已静默) | Unsilence, Mark resolved (取消静默 / 标记已处理) | back to `open` / `resolved` |
| Resolved (已恢复) | Silence (静默) | `silenced` (silenced again) |

After a successful action the page refreshes and shows a notice. State is written to RCA's `data/silenced.json` and survives restarts.

> "Silence" (静默) changes only the operational state; it does not delete evidence and does not affect subsequent diagnosis.

### 8.3 Reading Evidence

- Each evidence item shows `evidence_id`, `signal`, source kind, layer, resource, time, and description;
- When expanded, it shows `evidence_id`, `observed_at`, `layer / kind`, `resource`, `correlation_id`, `task_id`, `source_event_ids`, `mode`, and the raw payload;
- `source_event_ids` can be used against the platform's `/api/v1/events` to look up the raw event;
- ★ means the evidence is referenced by the current Top-1 candidate;
- When there is no evidence, the page states that the data source is disabled or there is no anomaly in the window; it never fabricates content.

### 8.4 Impact Scope

- `counts.tasks / services / containers` give the counts;
- The `scope` list shows resource, type, relation, `depth`, and status;
- `depth=1` is usually one hop away, `depth=2` is an extended impact range;
- Clicking "Topology" (拓扑) jumps to the topology page and focuses that resource.

### 8.5 Metric Charts

- Provided only for container resources;
- Charts include threshold lines (e.g. memory limit, PSI threshold);
- When the focus resource is not a container, a note says charts are only provided for container resources (仅容器类资源提供曲线);
- Metric data comes from Prometheus / cAdvisor; when unavailable, an error and guidance are shown.

---

## 9. Root Cause Diagnosis

Route: `/diagnosis`

### 9.1 Purpose

Run rule matching for a given anchor and time window, and output root cause candidates Top-N in descending Evidence Match order.

### 9.2 Inputs

| Control | Description |
|---|---|
| Anchor type (锚点类型) | `correlation_id` (a single Agent task) or `resource_id` (a system-layer resource) |
| Input field (输入框) | `correlation_id` example `d38fc66c8364`; `resource_id` must include the type prefix, e.g. `container:7196bcad3bc1` |
| Time window (时间窗) | 15 minutes / 1 hour / 6 hours |
| Top-N | 1–5 |
| Example inputs (示例输入) | Each of the four scenarios offers shortcut buttons for its `correlation_id` and `resource_id` |
| Run diagnosis (执行诊断) | Submit the request |

Input validation:

- Empty values prompt "please enter a correlation anchor / resource ID" (请输入关联锚点 / 资源标识);
- If the `resource_id` contains no `:`, it prompts "the resource ID should include a type prefix" (资源标识应包含类型前缀).

### 9.3 Results Area

| Block | Content |
|---|---|
| Summary cards (汇总卡) | Number of root cause candidates, evidence items used in scoring, Top-1 score, time window, affected task count |
| Root cause candidates Top-N (根因候选 Top-N) | Title, severity, Evidence Match, root cause identifier, rule version; click to switch candidates |
| Five-dimension score (五维评分) | Rule evidence hit, temporal precedence, resource adjacency, signal strength, independent evidence count; each shows score / max / detail |
| Remediation suggestions (处置建议) | `result.suggestions` of the current candidate; each contains basis / action / risk |
| Cited evidence (引用证据) | `evidence_ids` of the current candidate; ★ marks the evidence that hit |
| Candidate ranking (候选排序) | Click a candidate to see its full details |
| Impact scope (影响范围) | Affected tasks and resources; can jump to topology |
| Layered timeline (分层时间线) | Events within the diagnosis window |

### 9.4 How to Interpret

1. **First check whether Top-1 lands on the layer you expect**: container / VM / application;
2. **Then look at the five-dimension breakdown**: a low `rule_match` means key evidence is missing; if `temporal_precedence` is 0/0, the rule has no temporal constraint;
3. **Cross-check evidence IDs**: every conclusion can be found in the evidence list;
4. **Look at `sources.notes`**: when the platform is unavailable, it states how many fixture evidence items were injected;
5. **Do not treat the score as a probability**: 99 means the evidence hits are sufficient, not a 99% probability;
6. **When there are no results**: first confirm there are events in the window, the data source is available, and the anchor is correct.

### 9.5 Rule Library

The bottom of the page shows the four rules returned by `GET /api/v1/rules`:

- `container_oom`
- `cpu_contention`
- `tool_failure`
- `gpu_memory_exhaustion`

Click a rule button to focus on it; the card shows clause weights, `after` constraints, and expandable `rule / evidence / correlation / result` YAML structures plus remediation suggestions. Adding a rule only requires adding YAML; no changes to the Rule Engine code are needed.

---

## 10. Demo Path

### 10.1 The Four Scenarios

| Scenario | correlation_id | Focus resource | Rule | Expected conclusion |
|---|---|---|---|---|
| Case1 Container OOM (容器 OOM) | `d38fc66c8364` | `container:7196bcad3bc1` (tool-service) | `container_oom` | Container memory exhausted |
| Case2 CPU contention (CPU 争抢) | `cf6d4dfcd64a` | `container:e5d6f856a747` (cpu-stress) | `cpu_contention` | CPU resource contention |
| Case3 Tool failure (工具失败) | `8da4d26c78f6` | `container:e6eab2f12b53` (toxiproxy) | `tool_failure` | Agent tool call failure |
| Case4 GPU memory exhaustion (GPU 显存耗尽) | `85bcc7f9b016` | `gpu:mock-gpu0` | `gpu_memory_exhaustion` | GPU memory exhausted |

> These IDs come from demo fixtures that have been persisted to disk; in a real environment each task has a different `correlation_id`, so use the actual value returned.

### 10.2 Recommended Demo Order

1. **Health page**: baseline is all green, showing resources and tasks are normal;
2. **Case1**: inject OOM → health page turns red → "container memory exhausted" appears in the incident list → open details for the evidence chain and five-dimension scores → remediation suggestions;
3. **Case2**: inject CPU stress → PSI / throttling evidence → CPU contention Top-1;
4. **Case3**: shut down the tool proxy → `tool.result` error → tool failure Top-1;
5. **Case4**: Mock DCGM injection → memory utilization > 90% → GPU memory exhaustion Top-1;
6. **Topology page**: show the Host → VM → Container → Service → Task / GPU resource relationships;
7. **Diagnosis page**: enter a `correlation_id` manually; show the rule library and candidate ranking.

### 10.3 Demo in Fixture Mode

Without a backend:

```bash
cd console
VITE_DATA_SOURCE=fixture npm run dev
# or build:
VITE_DATA_SOURCE=fixture npm run build
```

The page shows `FIXTURE REPLAY`. All response structures match the API, and event times are shifted to "the last N minutes" to make time-window demos easier.

---

## 11. Command Line (CLI)

### 11.1 Build

```bash
cd rca
go build -o bin/tracesphere ./cmd/tracesphere
```

### 11.2 Common Commands

```bash
# Service + Console
./bin/tracesphere serve --listen :8010 --console ../console/dist

# Diagnosis
./bin/tracesphere diagnose --correlation-id <corr> --window 10m
./bin/tracesphere diagnose --resource-id container:<id> --window 10m
./bin/tracesphere diagnose --scenario case1-oom

# Incidents / health / topology / rules
./bin/tracesphere alerts --window 10m
./bin/tracesphere alerts --severity critical --rule container_oom
./bin/tracesphere health --window 15m
./bin/tracesphere topo --focus container:<id>
./bin/tracesphere rules

# JSON output (for scripts)
./bin/tracesphere diagnose --scenario case1-oom --json
./bin/tracesphere alerts --json
```

### 11.3 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TRACESPHERE_PLATFORM_URL` | `http://127.0.0.1:8000` | Platform address |
| `TRACESPHERE_PLATFORM_TOKEN` | empty | Platform token |
| `TRACESPHERE_PROMETHEUS_URL` | `http://127.0.0.1:9090` | Prometheus address |
| `TRACESPHERE_RCA_FIXTURE` | empty | `1` forces fixtures |
| `TRACESPHERE_RCA_SCENARIO` | empty | Fixture scenario |

### 11.4 Reading the Output

The `diagnose` text output contains:

- Time window and data source;
- `correlation_id` / `resource_id`;
- `[1]` Top-1 title, Evidence Match, rule version, severity;
- Root cause and explanation;
- Five-dimension score breakdown;
- Evidence list (ID, signal, kind, resource, time, value);
- Remediation suggestions;
- Alternative candidates;
- Note: Evidence Match is a rule-evidence hit score, not a probability.

`--json` output matches the Diagnosis object in [API.md §4.5](../../rca/docs/API.md).

---

## 12. Data Sources and Authenticity Markers

### 12.1 Two Build Modes

| Mode | Badge | Data source | Use case |
|---|---|---|---|
| api | `API LIVE` | RCA `/api/v1` | Real environment / integration testing |
| fixture | `FIXTURE REPLAY` | `src/mocks/*.json` | Demos / screen recording without a backend |

The mode is decided at build time by `VITE_DATA_SOURCE` and is read-only at runtime. Switching requires restarting the dev server or rebuilding.

### 12.2 Why api Mode Does Not Fall Back Automatically

This is deliberate: reviewers / operators must be able to tell "real data" from "replay data" at a glance. When a request fails in api mode, the page shows:

- The request path;
- The HTTP status;
- Handling guidance;
- The command to switch to fixture.

It never silently switches to fixtures.

### 12.3 Source Status

The footer / header shows:

- `platform: 真实 / 降级 / 未启用`;
- `prometheus: 真实 / 降级 / 未启用`;
- `fixture: 回放 / 未启用`.

In other words, each source is reported as real (真实), degraded (降级), or disabled (未启用); the fixture source is reported as replay (回放) or disabled (未启用). The diagnosis response also states in `sources.notes` how many evidence items were injected. Check the source status before reading conclusions.

---

## 13. Common Tasks

### 13.1 Investigate a Failed Agent Task

1. Get the `correlation_id` from the agent-service response or logs;
2. Open the diagnosis page, select `correlation_id`, enter the ID, and set the time window to 15 minutes;
3. Check whether Top-1 hits; check which of the five dimensions is missing;
4. Open the cited evidence and confirm `signal`, resource, and time;
5. If the evidence is insufficient, switch to the incident list and search for that `correlation_id` to see whether a complete correlation cluster exists;
6. Act on the remediation suggestions, then mark Acknowledged (确认) / Resolved (已处理) in the incident details.

### 13.2 Go from an Incident to the Topology

1. On the incident details page, click "View in topology" (在拓扑中查看);
2. The topology page will focus `focus_resource`;
3. In the drawer, view adjacent resources, related events, and metrics;
4. To see upper-layer impact, switch L1 / L2.

### 13.3 Check Whether a Container Is Abnormal

1. On the health page, filter "Containers only" (仅容器) and sort by "failed task count" or "health score";
2. Click "Diagnose" (诊断) on a card to enter the diagnosis page with the `resource_id` prefilled;
3. Or click "Topology" (拓扑) to see its parent VM and adjacent services.

### 13.4 Review Incident Operational State

1. Filter the incident list by "Open only" (仅未处理);
2. Open the details and perform "Acknowledge" (确认) or "Mark resolved" (标记已处理);
3. Silence suits known drill windows; silencing does not delete evidence;
4. After unsilencing, the incident returns to `open`.

### 13.5 Replay a Scenario

1. Choose a scenario from "Demo path" (演示路径) in the top bar;
2. Health / topology / diagnosis automatically carry the `correlation_id` / `resource_id`;
3. In a fixture build, all pages use fixtures directly;
4. In an api build, the real data for that scenario must exist; otherwise the page reports that there is no focus resource.

---

## 14. FAQ

| Question | Cause | Fix |
|---|---|---|
| The page does not open | RCA is not running / wrong port / reverse proxy not configured | Check `systemctl status tracesphere-rca`, `curl http://<host>:8010/` |
| The page returns 401 | RCA has a token enabled | Reopen with `?token=<RCA_TOKEN>` |
| The page shows "cannot connect to the diagnosis service" (无法连接诊断服务) | api mode request failed | Check 8010, `VITE_RCA_BASE_URL`, and the network; or switch to a fixture build |
| The data source badge stays FIXTURE | `VITE_DATA_SOURCE=fixture` was set at build time | Rebuild in api mode |
| Diagnosis returns no results | No evidence in the window / data source disabled / wrong anchor | Widen the time window; check `sources` on the health page; verify the ID |
| The evidence list is empty | The correlation cluster has no evidence or its source is disabled | Check `/api/v1/health` and `sources.notes` |
| The incident list is empty | No correlation clusters / window too narrow | Widen to 24 hours; confirm the scenario has been injected |
| Sub-scores do not add up to the total | The rule has no temporal constraint, so the denominator is 85 | This is the normalization design; see §4.5 |
| Times differ from local time | Pages are uniformly UTC | Convert to your local time zone; check node NTP |
| The topology has no process layer | No `process` nodes collected | Set `VMAGENT_REPORT_PROCESS=1` and restart the probe |
| The topology has no GPU | mock_gpu not enabled, or the data source is real ZSvirt without a GPU | Enable `TRACESPHERE_MOCK_GPU=1` on the platform; confirm mock-dcgm is running |
| Metric charts are empty | Focus resource is not a container / Prometheus unavailable | Switch to a container; check `PROM_BIND` and 9090 |
| Incident states are lost after restart | The `silenced.json` path is not writable | Check the RCA working directory and `data/` permissions |
| Very little data for the 6h window in fixture mode | Fixtures cover only about 15 minutes, with times shifted to the recent past | This is expected behavior |
| The incident badge in the top-right corner does not disappear | There are still incidents in `open` state | Acknowledge / resolve them on the details page |

---

## 15. Usage Boundaries

1. **Evidence Match is not a probability**: 99 means the evidence hits are sufficient, not a 99% accuracy rate; the project does no probability calibration.
2. **health_score is display-only**: it does not participate in RCA; do not compare it with Evidence Match.
3. **The four scenarios are controlled results**: 99 / 85 / 67 / 89 apply only to the corresponding controlled faults and collection configuration, not as general accuracy.
4. **Case3 boundary**: in the 2026-09-30 acceptance run, all evidence was application events; there was no transport-layer evidence. The tool-failure conclusion still holds, but do not state it as "network transport anomaly proven".
5. **Case4 boundary**: Mock DCGM is a degraded data source; metric names are `ts_gpu_*`; the semantics are compatible but it is not real DCGM; no real GPU validation has been done.
6. **Read-only ZSvirt**: platform does not call ZSvirt write APIs; this is guaranteed by code, not by account permission restrictions.
7. **Incident capability boundary**: there is no Alertmanager; the current capability is self-built correlation-cluster aggregation + three-state operations + silence, and does not include grouping / inhibition / notification channels.
8. **Console has no user system**: only a static token, with no roles or auditing; production multi-user use requires external SSO / a reverse proxy.
9. **Data retention**: the platform uses a single SQLite file; resetting the database loses historical evidence, so back it up before a demo.

---

## 16. Glossary

| Term | Description |
|---|---|
| Agent task (Agent 任务) | A single "tool call + inference" flow executed by agent-service |
| AppEvent | Structured application events reported directly by agent-service |
| Correlation cluster (关联簇) | A group of events and evidence under the same time window and the same resource / anchor |
| Evidence chain (证据链) | The traceable path from raw event to evidence to diagnosis conclusion |
| Evidence Match | Five-dimension rule-evidence hit score (0–100, not a probability) |
| fixture | Replay data captured from real drills |
| Mock DCGM | A simulated memory-metric source for environments without a GPU |
| PSI | Linux Pressure Stall Information; CPU / memory / IO pressure |
| cgroup v2 | Container resource control and accounting interface |
| Degraded mode (降级模式) | The available path when a data source or collection capability is unavailable |
| spool | Local retry queue on vm-agent when reporting fails |

---

## 17. Quick Index

| I want to... | Where to go |
|---|---|
| See whether everything is healthy overall | Health page (健康页) |
| See resource relationships | Topology page (拓扑页) |
| Find the cause of a task failure | Diagnosis page (诊断页), enter the `correlation_id` |
| See the evidence behind an incident | Incident list (告警列表) → Details (详情) |
| Acknowledge / silence an incident | Buttons on the incident details page |
| See rules and weights | "Rule library" (规则库) at the bottom of the diagnosis page |
| Demo without an environment | `VITE_DATA_SOURCE=fixture` |
| Get diagnosis results in a script | `tracesphere diagnose ... --json` |
| Tell real from replay | Top bar badge + footer source bar |

---

*Document version: v1.0 (2026-10-27). Update this document whenever the interface or API changes.*
