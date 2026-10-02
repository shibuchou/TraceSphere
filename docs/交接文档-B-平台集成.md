# TraceSphere 平台侧交接文档

> 交接范围：成员 B —— 平台集成 / 数据模型 / 关联引擎（`tracesphere/platform/`）
> 内部文档：含服务器与环境信息，**禁止放入比赛提交材料**（大赛匿名化要求）
> 敏感凭据不写入本文档：SSH 走本机密钥，ZSvirt 密码走环境变量 `ZSVIRT_PASSWORD`

---

## 1. 文档信息

| 项目 | 内容 |
|---|---|
| 项目名称 | TraceSphere — 面向 ZSvirt 虚拟机内容器与智能体工作负载的全栈可观测平台 |
| 交接模块 | `tracesphere/platform/`（成员 B：平台集成 / 数据模型 / 关联引擎） |
| 交出方 | 成员 B |
| 接收方 | 成员 C / 后续平台维护者 |
| 交接日期 | 2026-09-20 |
| 文档版本 | v1.0 |
| 对应方案 | `方案初版.md` v0.4（§4 ZSvirt 集成、§5 资源模型与关联引擎、§5.4 Schema v1） |
| 前置文档 | `开工交接-B与C.md`（A 的环境与访问说明） |
| 代码位置 | 本机 `opencodex/tracesphere/platform/`；服务器 `GPU1:~/tracesphere/platform/`（已同步） |

---

## 2. 交接概述

### 2.1 交接范围

本次交接覆盖 B 的 W1 全部交付以及 W2 的现有基础：

1. ZSvirt 接入：`RESTProvider`（真实）+ `FixtureProvider`（回放/降级），同一 Domain Model；
2. Resource Registry：Host / VM / 网络 / 存储 / 镜像等资源与资源图落库（SQLite WAL）；
3. Agent Registration：`POST /api/v1/agents/register` 的 VM 身份绑定；
4. Event / Evidence Store：Schema v1 归一化、双时间戳、身份补全、按 `correlation_id / resource_id / 时间窗` 查询；
5. Correlation Engine 最小版：时间窗 + 资源锚点 + 资源图拓扑扩展，输出 Cluster + Evidence；
6. HTTP API（`/api/v1/*`，stdlib 实现）与本地/服务器运行工具链；
7. 真实 ZSvirt fixtures（13 个集合）与真实环境实测记录。

**不在交接范围**：vm-agent（成员 A）、RCA Rule Engine / Web Console（成员 C）、Prometheus/Loki 运维（成员 A）。

### 2.2 当前状态总览

| 工作项 | 状态 | 说明 |
|---|---|---|
| ZSvirt 双轨 Provider | ✅ 完成 | 真实 REST 已在 GPU1 联调 |
| Resource Registry + 资源图 | ✅ 完成 | 14 资源 / 15 边（真实环境实测） |
| Agent Registration 接口 | ✅ 完成 | 契约见 §6，等待 A 的 vm-agent 接入 |
| Event / Evidence Store | ✅ 完成 | 47 个单测覆盖 |
| Correlation Engine 最小版 | ✅ 完成（W1 范围） | W2 需规则化与多跳扩展 |
| HTTP API + 运行工具链 | ✅ 完成 | 真实 REST HTTP 冒烟通过 |
| 真实 fixtures 抓取 | ✅ 完成 | `fixtures/_capture.json` `provisional=false` |
| vm-agent / agent-service 实际接入 | ⏳ 待 A 侧对接 | 接口已就绪，见 §11 |
| systemd 常驻部署 | ⏳ W2 | 当前用 nohup/前台运行 |
| W2 关联规则化 / Evidence Snapshot | ⏳ 未开始 | 见 §11 待办 |

---

## 3. 交付物清单

### 3.1 代码

| 路径 | 说明 |
|---|---|
| `platform/run.py` | 服务入口（CLI 参数 / 环境变量 / 启动同步） |
| `platform/tsplatform/` | Python 包（零第三方依赖，Python 3.8+） |
| `platform/tsplatform/zsvirt/` | `base.py`（Domain Model）、`mapper.py`（响应→领域模型）、`rest.py`、`fixture.py` |
| `platform/tsplatform/api.py` | `/api/v1/*` HTTP 接口（stdlib `ThreadingHTTPServer`） |
| `platform/tsplatform/app.py` | 应用装配（stores + provider + registry + correlation） |

完整文件清单见 §13.1。

### 3.2 文档

| 文件 | 说明 |
|---|---|
| `platform/README.md` | 运行、配置、API 契约、部署与联调说明（主文档） |
| `platform/fixtures/README.md` | 真实抓取信息、真实字段注意事项、刷新方式 |
| `platform/fixtures/_capture.json` | 抓取元数据：时间、路径、total、时钟偏差 |
| 本文档 | 交接说明（仅本机工作目录） |

### 3.3 工具

| 工具 | 用途 | 运行位置 |
|---|---|---|
| `tools/capture_fixtures.py` | 抓取真实 ZSvirt 响应为 fixtures + 时钟检查 | GPU1 |
| `tools/probe_paths.py` | 候选 API 路径探测（新增集合时用） | GPU1 |
| `tools/verify_rest.py` | REST 模式全链路验证（临时 DB，打印资源/图/告警） | GPU1 |
| `tools/rest_http_smoke.sh` | REST 模式起服 + HTTP 接口冒烟 | GPU1 |
| `tools/smoke.py` | 本地垂直切片冒烟（fixtures→注册→事件→关联→证据） | 任意 |

### 3.4 数据（fixtures）

13 个集合的真实响应原样保存在 `platform/fixtures/*.json`，由 `FixtureProvider` 回放；场景覆盖机制为
`fixtures/<scenario>/同名文件`（配置 `zsvirt.fixture_scenario`）。集合与路径对应关系见 `fixtures/README.md`。

### 3.5 测试

`platform/tests/` 共 47 个单测：`unittest`，无第三方依赖。

```bash
cd platform
python -m unittest discover -s tests -t . -v
```

---

## 4. 系统架构与模块说明

### 4.1 数据流

```text
ZSvirt REST（真实）/ fixtures（回放）
    └─ RESTProvider / FixtureProvider ──> zsvirt/mapper.py ──> Snapshot（统一 Domain Model）
                                                │
                                     registry.ResourceRegistry
                                                │
                    resources / resource_edges（SQLite WAL）
                                                ▲
AppEvent / vm-agent / Schema v1 ──> api /events ──> ingest.EventIngest（归一化+身份补全）
                                                │
                                          events 表
                                                │
                            correlate.CorrelationEngine（correlation_id + 时间窗 + 拓扑）
                                                │
                                     clusters / evidence 表 ──> C 的 RCA Rule Engine
```

### 4.2 模块职责

| 模块 | 职责 | 关键函数 |
|---|---|---|
| `config.py` | JSON 配置 + 环境变量覆盖 + 路径解析 | `load_config`、`resolve_zsvirt_password` |
| `db.py` | SQLite WAL、迁移、事务、表计数 | `Database.init/tx/query` |
| `domain.py` | 资源 ID 规范、关系词表 | `vm_id`、`container_id`、`task_id`、`REL_*` |
| `schema.py` | Schema v1 归一化（三种输入） | `normalize_event` |
| `store_resources.py` | 资源/边 upsert、查询、子图 | `upsert`、`subgraph`、`get_by_uuid` |
| `store_events.py` | 事件入库（dedup）、时间窗查询 | `insert`、`query`、`set_cluster` |
| `store_evidence.py` | 证据/关联簇存取（幂等合并） | `EvidenceStore.insert`、`ClusterStore.upsert` |
| `store_agents.py` | Agent 注册信息 | `upsert`、`get_by_vm_uuid` |
| `registry.py` | Provider → 资源图同步（幂等）+ 告警/事件摄入 | `ResourceRegistry.sync` |
| `ingest.py` | 身份补全（container/service/task）、双时间戳 | `EventIngest.ingest(_many)` |
| `correlate.py` | 关联簇 + 证据生成 | `CorrelationEngine.correlate` |
| `zsvirt/mapper.py` | ZStack 响应 → 资源/边/告警/事件 | `snapshot_from_raw`、`alarm_inventories_to_events` |
| `api.py` | HTTP 路由、鉴权、CORS | `serve`、`TraceSphereHandler` |

### 4.3 关键设计决策（接手必读）

1. **统一的是 Schema / Identity / Evidence，不是物理管道**（方案 §2.1）：指标走 Prometheus、日志走 Loki（P1）、事件/证据/资源走 SQLite。
2. **Provider 双轨共享 mapper**：`mode=real|mock` 只是数据来源，上层零分支；新增 ZSvirt 字段只改 `mapper.py`。
3. **事件身份补全在 ingest 完成**：AppEvent 的 `attributes.container_id` 会被识别，自动建 Container/Service/Task 资源与 `runs_on` 边，保证关联引擎立刻可用。
4. **Evidence 由 B 产出、RCA 由 C 决策**：B 不做根因判断（方案 §6.1）；`evidence.signal` = 原始 `event_type`，C 的规则按 signal/kind/条件匹配。
5. **单写者 SQLite WAL**：HTTP 线程各持连接，写操作经 store；批量写走 `db.tx()`。
6. **告警降噪**：`/zwatch/alarms` 是告警定义，默认只把 `status=Alarm` 的条目转事件；告警运营交给 Alertmanager（P1）。
7. **零第三方依赖**：平台不引入 FastAPI/Flask，保证 GPU1 上 `python3` 直接运行；解析告警 YAML 是 C 的职责。

---

## 5. 数据契约

### 5.1 Schema v1（冻结，方案 §5.4）

```text
schema_version   v1
origin           zsvirt | ebpf | cgroup | cadvisor | app | fluentbit
mode             real | mock
observed_at      事件实际发生时间（RFC3339 UTC）
ingested_at      平台接收时间（RFC3339 UTC）
type             resource | metric | event | alert | evidence | diagnosis
event_type       子类型（平台扩展列，证据匹配用，如 memory.events.oom_kill / task.failed）
resource_id      资源实体 ID
correlation_id   跨层关联 ID（应用层事件携带）
trace_id / task_id / severity(info|warning|major|critical)
source           产生组件（平台扩展列）
cluster_id       关联簇 ID（平台扩展列，关联后回填）
payload          类型相关载荷（未知字段原样保留）
```

> 时间统一存 UTC；`observed_at` 与 `ingested_at` 必须区分（跨层关联依赖时间窗）。

### 5.2 资源 ID 与关系词表

- ID 规范：`<kind>:<key>`，如 `vm:<zsvirt-uuid>`、`host:<uuid>`、`container:<64位id>`、`service:<name>`、`task:<task_id>`、`process:<pid>:<start_time>`；
- 词表：`contains / assigned_to / attached_to / uses / has_volume / over / provides / runs_on / calls / spawns`；
- `GET /api/v1/meta` 返回完整枚举，C 的 G6 拓扑直接按 relation 渲染。

### 5.3 事件摄入支持的三种格式

1. **AppEvent（方案 §3.4）**：`event_type / task_id / correlation_id / service / timestamp / status / attributes`；
2. **Schema v1**：带 `schema_version` 的完整事件，按原样落库；
3. **vm-agent 松散事件**：任意含 `event_type` 的 JSON，未知字段进 `payload`；调用方通过 `default_origin` 指定 `ebpf/cgroup`。

去重：请求体带 `dedup_key` 时同一 key 只入库一次；ZSvirt 告警/事件使用 uuid 派生 key，重复 sync 幂等。

### 5.4 数据库表

| 表 | 说明 | 关键索引 |
|---|---|---|
| `resources` | 资源实体 | kind / cluster_id / vm_id / host_id / container_id / name / correlation_id |
| `resource_edges` | 资源图边（主键 src+dst+relation） | dst_id / relation |
| `events` | Schema v1 事件 | observed_at / resource_id / correlation_id / event_type / cluster_id / task_id / dedup_key(unique) |
| `evidence` | 证据条目 | cluster_id / resource_id / correlation_id / signal / dedup_key(unique) |
| `clusters` | 关联簇（cluster_key 唯一，幂等） | correlation_id / resource_id |
| `agents` | Agent 注册 | configured_vm_uuid / resource_id |
| `sync_runs` | Provider 同步记录（/health 可见） | — |

---

## 6. HTTP API（`/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康 + DB counts + last_sync（默认免 token） |
| GET | `/meta` | Schema 字段、枚举、资源类型、关系词表、端点清单 |
| POST | `/agents/register` | Agent 注册（方案 §5.5），返回 `resource_id` 与 VM 资源 |
| GET | `/agents` | 已注册 Agent 列表 |
| POST | `/events` | 事件入库（单条 / `{events:[...]}` 批量） |
| GET | `/events` | 查询（correlation_id / resource_id / task_id / event_type / severity / cluster_id / origin / source / from / to / limit / offset） |
| POST | `/resources/sync` | ZSvirt provider → Registry → 资源图（幂等） |
| GET | `/resources`、`/resources/{id}`、`/resources/{id}/graph` | 资源查询 / 详情+边 / 子图（depth≤5，direction） |
| POST/GET | `/evidence` | 手工写入 / 按 cluster、correlation、resource、signal、时间窗查询 |
| GET | `/clusters`、`/clusters/{id}` | 关联簇列表 / 簇+证据+源事件 |
| POST | `/correlate` | 对时间窗执行关联（默认最近 15 分钟） |
| GET | `/context` | RCA 聚合入口：events + evidence + clusters + resources + graph |

### 6.1 Agent Registration 请求（A 侧对接）

```json
POST /api/v1/agents/register
{
  "agent_id": "vm-agent-63bbb461",
  "configured_vm_uuid": "63bbb4613a524e4e97090600af03da93",
  "machine_id": "</etc/machine-id>",
  "dmi_uuid": "<DMI UUID>",
  "hostname": "workload-vm",
  "ips": ["10.100.0.181"],
  "version": "0.1.0"
}
```

返回：`{"agent_id","resource_id","vm","registered_at","ingest":{"events_endpoint":"/api/v1/events"}}`。
`configured_vm_uuid` 必须显式注入，不假定 ZSvirt UUID = Guest DMI UUID。

### 6.2 鉴权与 CORS

- `api.token` 非空时，除 `/health` 外需 `Authorization: Bearer <token>` 或 `X-API-Token`；当前开发配置为空。
- `api.cors_origins` 默认 `["*"]`，C 的 React dev server 可直接跨域。

---

## 7. 环境与访问

### 7.1 服务器层级

```text
本地 Windows（代码开发）
  └─ GPU1（x86_64 KVM 宿主机，<kvm-host>:2232，用户 <user>）
       └─ zsvirt-mgmt（ZSvirt 管理节点，192.168.122.123，root / 见《开工交接-B与C.md》）
            └─ workload-vm（业务 VM，10.100.0.181，ubuntu / 同上）
```

### 7.2 登录方式（已配置免密）

- 本机已生成专用密钥 `~/.ssh/gpu1_ed25519`，其公钥已追加到 GPU1 `~/.ssh/authorized_keys`；
- 本机 `~/.ssh/config` 已添加别名：`ssh GPU1` 即可登录；
- GPU1 主机密码未写入任何文件（仅用于一次性公钥安装）；
- 若密钥丢失：需重新获取 GPU1 访问权限并执行一次公钥安装。

### 7.3 ZSvirt API（实测确认）

- 入口：`http://192.168.122.123:8080/zstack/v1`（8080 是 API；443 是 UI nginx）；
- 登录：`PUT /accounts/login`，body `{"logInByAccount":{"accountName":"admin","password":"<sha512(明文)>"}}`；
- 认证头：`Authorization: OAuth <session-uuid>`（会话过期自动重登录）；
- 已验证路径：`vm-instances / hosts / zones / clusters / images / l3-networks / l2-networks / l2-networks/port-groups / primary-storage（单数）/ backup-storage（单数）/ instance-offerings / zwatch/alarms / zwatch/events`；
- 关键 UUID（数据源）：见 `platform/fixtures/_capture.json` 的 `known_uuids`；
- 时钟：抓取时偏差 -0.85s（±5s 关联窗内），每次抓取记录 `_capture.json.clock.skew_seconds`。

### 7.4 代码位置与同步

| 位置 | 路径 | 状态 |
|---|---|---|
| 本机 | `<本机开发目录>\tracesphere\platform\`（见仓库根） | 主开发副本 |
| GPU1 | `~/tracesphere/platform/` | 已同步（2026-09-20） |

同步方式：本地 robocopy 到临时目录（排除 `__pycache__`/`data`）后 `scp -r`；或 `rsync`（GPU1 端）。

---

## 8. 部署与运行

### 8.1 本地 Fixture 模式

```bash
cd platform
python run.py --provider fixture --host 127.0.0.1 --port 8000
python tools/smoke.py
```

### 8.2 GPU1 真实 REST 模式

```bash
ssh GPU1
cd ~/tracesphere/platform
export ZSVIRT_PASSWORD='<admin 密码>'
nohup python3 run.py --provider rest --host 0.0.0.0 --port 8000 --db data/tracesphere.db \
    > data/platform.log 2>&1 &
curl http://127.0.0.1:8000/api/v1/health
```

### 8.3 工具命令

```bash
# 抓取真实 fixtures（含时钟检查）
ZSVIRT_PASSWORD='...' python3 tools/capture_fixtures.py --out fixtures
# 探测候选 API 路径（新增集合时）
ZSVIRT_PASSWORD='...' python3 tools/probe_paths.py
# REST 全链路验证（临时 DB）
ZSVIRT_PASSWORD='...' python3 tools/verify_rest.py
# REST 起服 + HTTP 冒烟
ZSVIRT_PASSWORD='...' bash tools/rest_http_smoke.sh
```

### 8.4 配置与环境变量

配置文件：`config/platform.example.json`（可复制为 `config/platform.json`，已在 `.gitignore` 中）。

| 环境变量 | 作用 |
|---|---|
| `ZSVIRT_PROVIDER` | `rest` / `fixture` |
| `ZSVIRT_BASE_URL` / `ZSVIRT_ACCOUNT` / `ZSVIRT_PASSWORD` | ZSvirt 接入 |
| `ZSVIRT_FIXTURES` / `ZSVIRT_SCENARIO` | fixtures 目录 / 场景 |
| `TRACESPHERE_HOST/PORT/DB/LOG_LEVEL` | 服务与日志 |
| `TRACESPHERE_API_TOKEN` | API 鉴权 token |

---

## 9. 验收与测试

### 9.1 自动化测试

```text
Ran 47 tests in ~2.2s — OK
```

覆盖：时间/严重级工具、Schema 归一化、fixtures mapper（真实数据）、REST 客户端（伪服务器：登录哈希、分页、401 重登、路径错误）、存储层（幂等/去重/子图）、事件身份补全、关联引擎（Case 1 链、幂等、资源窗）、HTTP API（含 token 鉴权）、真实告警/事件形状。

### 9.2 真实环境实测记录（2026-09-20，GPU1）

| 项 | 结果 |
|---|---|
| REST sync | `ok=true`，14 资源 / 15 边 / 5 事件（1 条 `zsvirt.alarm` + 4 条 `zsvirt.event`） |
| 重复 sync | 幂等：`events_ingested=0`，`events_duplicated=5` |
| workload-vm 图 | host→vm→{volume, image, network} 齐全；`pg-demo → L2PortGroup → DSwitch` 层级正确 |
| HTTP 冒烟 | health / sync / graph / alarms / events 全部通过（`tools/rest_http_smoke.sh`） |
| fixtures 抓取 | 13 个集合全部成功，`provisional=false` |
| 时钟偏差 | -0.85s |

### 9.3 交接验收清单

- [x] 代码已同步 GPU1，47 单测全绿
- [x] `python tools/smoke.py` 本地跑通完整垂直链路
- [x] GPU1 真实 REST 联调 + HTTP 冒烟通过
- [x] 真实 fixtures 已回填并纳入测试
- [ ] A 侧 vm-agent 接入 `/agents/register` 与 `/events`（待联调）
- [ ] C 侧按 `/evidence`、`/context` 契约对接（待联调）
- [ ] 平台 systemd 常驻 GPU1（W2）

---

## 10. 已知问题与限制

| # | 问题 | 现状 / 规避 |
|---|---|---|
| 1 | VM IP 不在 ZSvirt 中（`vmNics` 无 ip，flat DHCP 由宿主机手工提供） | VM 资源 IP 以 Agent Registration 的 `ips` 合并为准 |
| 2 | `/l3-networks` 实际返回 `type=portGroup` | mapper 记录 `apiType/apiCollection`，层级用 `over` 边表达 |
| 3 | `/zwatch/alarms` 是告警定义，不是告警实例 | 只转 `status=Alarm` 条目；恢复事件未实现，后续交由 Alertmanager |
| 4 | `/zwatch/events` 无 `total` 字段 | `query()` 已兼容（缺省取实际条数） |
| 5 | 关联引擎为 W1 最小版：单跳拓扑、固定时间窗 | W2 规则化 + 多跳影响范围 |
| 6 | `evidence.signal` 依赖 A 的事件命名 | W1 接口冻结时需与 A 对齐（如 `memory.events.oom_kill`） |
| 7 | API 默认无 token、`/health` 免鉴权 | 演示环境按需设置 `TRACESPHERE_API_TOKEN` |
| 8 | 未提供 systemd/开机自启 | 当前 nohup；W2 补 unit 文件 |
| 9 | ZSvirt session 未做主动续期（仅 401 重登） | 长跑时依赖请求触发重登，可接受 |
| 10 | `fixtures` 含内网地址/UUID | 内部开发材料，提交前需按大赛匿名化要求处理 |

---

## 11. 待办事项（W2，按优先级）

1. **与 C 联调 RCA**：确认 `evidence.signal/kind/description/payload` 的匹配约定，按需在 `/context` 增加诊断所需的聚合字段；
2. **关联规则化**：把 `correlate.py` 的固定逻辑改为配置驱动（时间窗、拓扑方向、多跳），输出 Evidence Snapshot；
3. **影响范围**：沿资源图向下传播（VM→Container→Service→Task），输出受影响任务清单；
4. **接入 A 的 vm-agent**：验证 `/agents/register` 真实注册，接收 exec/exit/oom/retcp 事件并核对字段命名；
5. **systemd 常驻 GPU1** + 定时 sync（配置 `sync_interval_sec` 已预留，当前未启用）；
6. **性能**：事件表批量写入、按需清理与保留策略（当前无 retention）；
7. **安全收尾**：正式环境设置 API token、GPU1 防火墙仅暴露必要端口、fixtures 脱敏检查。

---

## 12. 风险与降级

| 风险 | 影响 | 对策 |
|---|---|---|
| ZSvirt 管理节点不可达 | 真实数据中断 | 切 `ZSVIRT_PROVIDER=fixture`，同一数据模型回放（演示稳定） |
| ZSvirt 时间跳变 | 跨层关联失效 | 每次抓取/启动检查 clock skew；必要时以 Agent 上报时间为准 |
| 会话过期 | sync 失败 | 客户端自动重登录一次；失败记录在 `sync_runs` 与 `/health.last_sync` |
| fixtures 与真实响应漂移 | 回放失真 | 定期 `capture_fixtures.py` 刷新并跑回归 |
| SQLite 单文件损坏/并发 | 数据丢失 | WAL + busy_timeout；数据文件在 `data/`（gitignore），演示前重抓 fixtures 即可重建 |

---

## 13. 附录

### 13.1 文件清单

```text
platform/
├── run.py
├── README.md
├── .gitignore
├── config/platform.example.json
├── fixtures/            # 13 个真实集合 + _capture.json + README.md
├── tsplatform/
│   ├── __init__.py  app.py  api.py  config.py  db.py  domain.py  schema.py  util.py
│   ├── store_resources.py  store_events.py  store_evidence.py  store_agents.py
│   ├── registry.py  ingest.py  correlate.py
│   └── zsvirt/{__init__,base,mapper,rest,fixture}.py
├── tools/
│   ├── capture_fixtures.py  probe_paths.py  verify_rest.py
│   ├── rest_http_smoke.sh  smoke.py
└── tests/               # 8 个测试模块 + common.py（夹具/临时库）
```

### 13.2 命令速查

```bash
# —— 本地 ——
cd platform
python run.py --provider fixture --port 8000
python tools/smoke.py
python -m unittest discover -s tests -t . -v

# —— GPU1 ——
ssh GPU1
cd ~/tracesphere/platform
export ZSVIRT_PASSWORD='...'
python3 tools/verify_rest.py
ZSVIRT_PASSWORD='...' bash tools/rest_http_smoke.sh
python3 tools/capture_fixtures.py --out fixtures
```

### 13.3 排障

| 现象 | 排查 |
|---|---|
| sync 全集合 HTTP 400 | Provider 未登录：确认 `RESTProvider.snapshot` 调用了 `ensure_login`；或密码错误 |
| 集合 404 | 用 `tools/probe_paths.py` 核对路径（存储类接口是**单数**） |
| 关联簇为空 | 检查事件 `observed_at` 是否在窗口内；`correlation_id` 是否一致；容器/服务资源是否已建边 |
| 证据查不到 | 系统层证据的 `correlation_id` 继承自簇；先 `GET /clusters?correlation_id=` 再按 `cluster_id` 查 |
| 重复事件 | ZSvirt 源带 `dedup_key`；AppEvent 如需去重请由生产方提供稳定 `event_id`/`dedup_key` |
| fixtures 缺文件 | `FixtureProvider.missing` 会记录在 sync 错误中；重跑 capture 脚本 |

### 13.4 术语

| 术语 | 说明 |
|---|---|
| Domain Model | 平台内部统一的资源记录（`ResourceRecord/EdgeRecord/Snapshot`），屏蔽 ZSvirt 字段 |
| Evidence | 证据条目（证据 ID、时间、来源信号、实体、描述、源事件 ID），RCA 的最小支撑单元 |
| Cluster | 关联簇，一组被判定相关的事件 + 其证据集合 |
| fixture 场景 | `fixtures/<scenario>/` 文件级覆盖，用于正常/故障/降级回放 |
