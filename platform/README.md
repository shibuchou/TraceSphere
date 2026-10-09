# TraceSphere Platform（成员 B）

平台集成 / 数据模型 / 关联引擎。对应方案 `方案初版.md` 第 4、5 章与 `开工交接-B与C.md` §3。

**边界**：不碰 UI，不写诊断规则，不负责 Prometheus/Loki 运维。B 的输出是「关联簇 + 结构化证据」，按 方案 §6.1 交给 C 做 RCA。

## 目录

```text
platform/
├── run.py                      # 服务入口
├── config/platform.example.json
├── tsplatform/
│   ├── app.py                  # 应用装配（stores + provider + registry + correlation）
│   ├── api.py                  # /api/v1/* HTTP 接口（stdlib，无第三方依赖）
│   ├── config.py               # JSON 配置 + 环境变量覆盖
│   ├── db.py                   # SQLite WAL + 迁移 + 索引
│   ├── domain.py               # 资源 ID / 关系词表
│   ├── schema.py               # Schema v1 归一化（三种输入格式）
│   ├── store_resources.py      # Resource Registry / 资源图
│   ├── store_events.py         # Event Store
│   ├── store_evidence.py       # Evidence / Cluster Store
│   ├── store_agents.py         # Agent Registration
│   ├── registry.py             # provider snapshot -> resources/edges 同步
│   ├── ingest.py               # 事件入库 + 身份补全（container/service/task）
│   ├── correlate.py            # Correlation Engine（W1 最小版）
│   └── zsvirt/                 # RESTProvider / FixtureProvider（同一 Domain Model）
├── fixtures/                   # 官方响应原样回放（当前为 provisional，见 fixtures/README.md）
├── tools/
│   ├── capture_fixtures.py     # GPU1 上抓取真实 ZSvirt 响应
│   └── smoke.py                # 本地垂直切片冒烟
└── tests/                      # 43 个单测（python -m unittest discover）
```

零第三方依赖，Python 3.8+（Windows / Linux 均可）。

## 快速开始（本地 Fixture）

```bash
cd platform
python run.py --provider fixture --host 127.0.0.1 --port 8000
# 或完整配置：
cp config/platform.example.json config/platform.json   # 按需修改
python run.py --config config/platform.json
```

启动后：

```bash
curl http://127.0.0.1:8000/api/v1/health
curl -X POST http://127.0.0.1:8000/api/v1/resources/sync
curl 'http://127.0.0.1:8000/api/v1/resources?kind=vm'
curl 'http://127.0.0.1:8000/api/v1/resources/vm:a1b2c3d456784b7d8e9f0a1b2c3d4e5f/graph?depth=2'
```

端到端冒烟（fixtures → 注册 → 事件 → 关联 → 证据）：

```bash
python tools/smoke.py
python -m unittest discover -s tests -t . -v
```

## 真实 ZSvirt（REST 模式）

> 管理节点地址与凭据见交接文档，**密码只走环境变量，不入库、不进日志、不写配置**（方案 §8）。

```bash
export ZSVIRT_PASSWORD='<admin 密码>'
python run.py --provider rest --base-url http://127.0.0.1:8080/zstack/v1 --host 0.0.0.0 --port 8000
```

- 登录：`PUT /accounts/login`，密码字段为 `sha512(明文)` hex；后续请求头 `Authorization: OAuth <session-uuid>`。
- 会话过期（HTTP 401/403 或错误码含 `SESSION/AUTH`）自动重登录一次。
- `zsvirt.paths` 可覆盖各集合查询路径；**已在真实 ZSvirt（2026-09-20）核验**：`vm-instances / hosts / zones / clusters / images / l3-networks / l2-networks / l2-networks/port-groups / primary-storage（单数）/ backup-storage（单数）/ instance-offerings / zwatch/alarms / zwatch/events`。
- `zsvirt.provider=fixture` 与 `rest` 输出同一 Domain Model，切换不修改上层代码。
- 时钟核验：管理节点与本机偏差 -0.85s，满足 ±5s 关联窗。

抓取真实 fixtures（在 GPU1 上执行）：

```bash
export ZSVIRT_PASSWORD='<admin 密码>'
python3 tools/capture_fixtures.py --out fixtures   # 原样落盘 + 更新 _capture.json
python3 tools/probe_paths.py                       # 候选 API 路径探测
python3 tools/verify_rest.py                       # REST 模式全链路验证（临时 DB）
```

脚本会：原样落盘官方响应 → 更新 `_capture.json`（provisional=false、时间、各集合 total、路径探测结果、时钟偏差 skew）。

## HTTP API 契约（`/api/v1`）

统一字段 Schema v1（方案 §5.4）：`schema_version / origin / mode / observed_at / ingested_at / type /
resource_id / correlation_id / trace_id / task_id / severity / payload`；
平台扩展列：`event_type`（子类型，证据匹配用）、`source`、`cluster_id`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康 + DB counts + last sync（默认免 token） |
| GET | `/meta` | Schema 字段、枚举、资源类型、关系词表、端点清单 |
| POST | `/agents/register` | vm-agent VM 身份绑定（方案 §5.5），返回 `resource_id` 与 VM 资源 |
| GET | `/agents` | 已注册 agent 列表 |
| POST | `/events` | 事件入库（单条 / `{events:[...]}` 批量），返回 inserted/duplicates/warnings |
| GET | `/events` | 按 `correlation_id / resource_id / task_id / event_type / severity / cluster_id / origin / source / from / to / order / limit / offset` 查询 |
| POST | `/resources/sync` | ZSvirt provider → Resource Registry → 资源图（幂等） |
| GET | `/resources` | 资源查询（kind/name/cluster_id/vm_id/host_id/state/q） |
| GET | `/resources/{id}` | 资源详情 + 出/入边 |
| GET | `/resources/{id}/graph` | 子图（`depth=1..5`、`direction=in/out/both`），节点含 placeholder（未注册资源） |
| POST | `/evidence` | 手工写入证据（测试 / 回填） |
| GET | `/evidence` | 按 `cluster_id / correlation_id / resource_id / signal / kind / from / to` 查询 |
| GET | `/clusters`、`/clusters/{id}` | 关联簇 + 证据 + 源事件 |
| POST | `/correlate` | 对时间窗执行关联，返回簇 + 证据 |
| GET | `/context` | RCA 聚合输入：events + evidence + clusters + resources + graph（C 的诊断页一口取数） |

### Agent Registration（A 的 vm-agent 调用）

```json
POST /api/v1/agents/register
{
  "agent_id": "vm-agent-a1b2c3d4",
  "configured_vm_uuid": "a1b2c3d456784b7d8e9f0a1b2c3d4e5f",
  "machine_id": "</etc/machine-id>",
  "dmi_uuid": "<DMI UUID>",
  "hostname": "workload-vm",
  "ips": ["10.0.0.10"],
  "version": "0.1.0"
}
```

返回 `{"agent_id","resource_id","vm","registered_at","ingest":{"events_endpoint":"/api/v1/events"}}`。
`configured_vm_uuid` 显式注入（cloud-init / 环境变量 / `/etc/tracesphere/agent.yaml`），**不假定 ZSvirt UUID = DMI UUID**。

### 事件入库支持的三种格式

1. **AppEvent（方案 §3.4）**：`event_type/task_id/correlation_id/service/timestamp/status/attributes`；
   `attributes.container_id` 会被识别（container 优先作为资源锚点），并自动建立
   `task runs_on service/container`、`service runs_on container` 边。
2. **Schema v1 完整事件**：`schema_version/origin/mode/observed_at/.../payload`，按原样落库。
3. **vm-agent 松散事件**：任意含 `event_type` 的 JSON，未知字段保留在 `payload`，`origin` 默认 `ebpf`（调用方指定）。

去重：请求体带 `dedup_key` 时同一 key 只入库一次（ZSvirt alarm/event 用 uuid 去重，重复 sync 不会翻倍）。

### 证据（C 的 RCA 输入）

- `evidence.kind`：`cgroup | ebpf | metric | app_event | log | zsvirt | topology`；
- `evidence.signal`：原始 `event_type`（如 `memory.events.oom_kill`、`task.failed`）——**命名与 A 的事件命名保持一致**，W1 接口冻结时对齐；
- `evidence.correlation_id`：簇的应用层锚点（系统层证据继承簇的 correlation_id，便于按任务取全量证据）；
- `source_event_ids` 指向原始事件，`/clusters/{id}` 可直接取回事件详情；每条诊断结论都应能引用证据 ID（方案 §5.4）。

## 关联引擎（W1 最小版）

```text
事件 → 时间窗(默认 ±5s) + 资源身份(cgroup/cadvisor/ebpf) + correlation_id(应用层)
     → 资源图拓扑扩展（focus 资源 1 跳邻居）
     → Cluster（幂等 cluster_key=事件ID集合哈希）
     → Evidence（signal/kind/描述/源事件ID）
```

- `POST /correlate` 默认分析最近 15 分钟；可传 `from/to/resource_id/correlation_id/window_seconds`。
- 同一簇重复执行不产生重复证据（dedup_key 幂等）。
- W2 在此基础上扩展：规则化时间窗、更多拓扑方向、Evidence Snapshot 快照。

## 资源模型与关联键

- 资源 ID：`<kind>:<key>`，如 `vm:<zsvirt-uuid>`、`host:<uuid>`、`container:<64位id>`、`service:<name>`、`task:<task_id>`、`process:<pid>:<start_time>`。
- 关系词表：`contains / assigned_to / attached_to / uses / has_volume / over / provides / runs_on / calls / spawns`。
- 关联键：VM = ZSvirt uuid（`configured_vm_uuid` 显式注入）+ machine-id / DMI uuid；容器 = container_id + cgroup；任务 = task_id + correlation_id。
- `GET /meta` 会返回完整词表，C 的 G6 拓扑可直接按 `relation` 渲染。

## SQLite WAL

单文件 `data/tracesphere.db`（配置 `platform.db_path`）。表：`resources / resource_edges / events / evidence / clusters / agents / sync_runs`。
索引覆盖 `timestamp(observed_at) / resource_id / correlation_id / event_type / cluster_id`（方案 §2.2），并额外索引 `task_id / kind / name / vm_id / host_id / dedup_key`。

## 配置

`config/platform.example.json` 可复制为 `config/platform.json`。环境变量覆盖：
`TRACESPHERE_HOST/PORT/DB/LOG_LEVEL`、`ZSVIRT_PROVIDER/BASE_URL/ACCOUNT/PASSWORD/FIXTURES/SCENARIO`、`TRACESPHERE_API_TOKEN`。

- `api.token` 非空时，除 `/health` 外都需要 `Authorization: Bearer <token>` 或 `X-API-Token`。
- `api.cors_origins` 默认 `["*"]`，C 的 React dev server 可直接跨域联调。
- `zsvirt.fixture_scenario` 指定后按 `fixtures/<scenario>/` 文件级覆盖，用于正常/故障/降级回放（方案 §4.2）。

## 部署到 GPU1（建议）

平台需要同时访问 ZSvirt 管理 API 与 VM 事件源，建议部署在 GPU1（KVM 宿主机）：

```bash
# 本地打包后 scp 到 GPU1，或直接在 GPU1 clone 仓库
cd tracesphere/platform
export ZSVIRT_PASSWORD='...'
nohup python3 run.py --provider rest --host 0.0.0.0 --port 8000 --db data/tracesphere.db \
    > data/platform.log 2>&1 &
curl http://127.0.0.1:8000/api/v1/health
```

systemd 单元（W2 整理）：`ExecStart=/usr/bin/python3 /opt/tracesphere/platform/run.py --config /etc/tracesphere/platform.json`。

## W1 状态

- [x] RESTProvider + FixtureProvider 同一 Domain Model
- [x] Resource Registry + 资源图落库（SQLite WAL + 方案要求索引）
- [x] Agent Registration 接口
- [x] Event/Evidence Store + 查询（correlation_id / resource_id / 时间窗）
- [x] Correlation Engine 最小版 + `/correlate`、`/context`
- [x] 本地 47 单测 + smoke 全绿
- [x] **GPU1 真实 REST 冒烟**：14 资源 / 11 边 / 1 条激活告警 + 4 条 ZWatch 事件入库，时钟偏差 -0.85s
- [x] **真实 fixtures 抓取**（`fixtures/_capture.json`，provisional=false）
- [ ] vm-agent / agent-service 实际接入（A 侧对接 `/agents/register` 与 `/events`）
- [ ] W2：关联规则化、Evidence Snapshot、与 C 的 Rule Engine 联调

### 真实环境注意（已处理/已记录）

1. **VM IP**：ZSvirt 的 `vmNics` 不记录 IP（10.0.0.0/24 的 flat DHCP 由宿主机手工提供）。
   VM 资源最终 IP 以 **Agent Registration 的 `ips`** 为准（注册时合并进 VM `attributes.ips`）。
2. **网络层级**：`/l3-networks` 实际返回 `type=portGroup`；`pg-demo → L2PortGroup → DSwitch` 用 `over` 边表达。
3. **告警语义**：`/zwatch/alarms` 是告警定义（18 条，仅 1 条 `status=Alarm`）。默认只把激活告警转成事件，dedup key 含状态与 `lastOpDate`；告警运营由 Alertmanager 承担（方案 §6.2）。
4. **时钟**：抓取脚本内置 clock check；管理节点曾发生时间跳变（交接文档 §3.4），每次抓取都会记录 `skew_seconds`。
