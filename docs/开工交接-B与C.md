# TraceSphere 开工交接说明（B / C）

> 内部文档（含服务器与账号信息）：**禁止放入比赛提交材料**（大赛匿名化要求）
> 维护：A ｜ 日期：2026-09-19 ｜ 详细环境记录见 `tracesphere/deploy/README.md`

---

## 1. 成员 A 交付状态

| 项目 | 状态 | 位置 / 说明 |
|---|---|---|
| ZSvirt 环境（管理节点 + 平台资源初始化） | ✅ 完成 | GPU1 嵌套部署，REST API 已验证（Gate 通过） |
| 业务 VM `workload-vm` | ✅ 完成 | ZSvirt 管理，10.100.0.181，4 vCPU / 4 GiB / 40 GiB |
| vm-agent（eBPF + PSI/cgroup） | ✅ 已 systemd 化 | 源码 `tracesphere/vm-agent/`；服务 `tracesphere-vm-agent`；事件：`/opt/tracesphere/evidence/vm-agent.log` |
| 样例 AI 负载（agent→tool→llama） | ✅ 全链路跑通 | `tracesphere/workload/`；VM 内 `/opt/tracesphere/workload` |
| 采集栈（Prometheus + cAdvisor + AppEvent） | ✅ 运行中 | 端口见 §2.4 |
| 故障注入脚本（OOM/CPU/网络） | ✅ 就绪 | `tracesphere/workload/faults/` |
| 三场景端到端演练 | ✅ 完成 | 报告 `tracesphere/docs/evidence/case{1,2,3}-*.md` |
| 探针开销 / 安装卸载 | ✅ 完成 | `vm-agent/deploy/`；报告 `docs/evidence/vm-agent-overhead.md` |

**结论**：A 的交付已全部完成（探针 / 负载 / 采集 / 故障注入 / 三 Case 演练 / 开销与卸载说明）；B / C 可全速开工。

---

## 2. 环境与访问信息

### 2.1 服务器层级

```text
本地（Windows）
  └─ GPU1（x86_64 KVM 宿主机，<kvm-host>:2232，user <user>，密钥 ~/.ssh/id_ed25519）
       └─ zsvirt-mgmt（ZSvirt 管理节点 VM，libvirt 管理，192.168.122.123，root / <password>）
            └─ workload-vm（ZSvirt 管理的业务 VM，10.100.0.181，ubuntu / <password>）
```

> ARM 服务器（worker02 / service3 / work01）不能跑 ZSvirt（官方仅 x86_64 镜像），本项目不用。
> GPU1 上有其他实验，请勿动其他 libvirt 域，仅在 zsvirt-mgmt / workload-vm 上操作。

### 2.2 登录方式（逐跳）

```bash
# 0) 本地：ssh config 里已有 GPU1 别名（Host GPU1 / <kvm-host> / 2232 / <user> / id_ed25519）
ssh GPU1

# 1) 在 GPU1 上进 ZSvirt 管理节点（控制台/SSH 二选一）
sshpass -p <password> ssh root@192.168.122.123          # SSH（推荐）
sudo virsh console zsvirt-mgmt                          # 串口控制台（备用）

# 2) 在 GPU1 上进业务 VM（GPU1 已加路由 10.100.0.0/24 via 192.168.122.123）
sshpass -p <password> ssh ubuntu@10.100.0.181
```

### 2.3 ZSvirt REST API（B 重点）

| 项 | 值 |
|---|---|
| API 入口 | `http://192.168.122.123:8080/zstack/v1`（**注意是 8080；443 只是 UI 的 nginx**） |
| 登录 | `PUT /accounts/login`，body `{"logInByAccount":{"accountName":"admin","password":"<sha512(明文)>"}}` |
| 认证头 | `Authorization: OAuth <session-uuid>` |
| 管理 UI | `https://192.168.122.123:443`（admin / <password>） |
| 重置密码 | MN 上 `zstack-ctl reset_password --password <new>` + `zstack-ctl restart_node` |

最小冒烟（在 GPU1 上执行）：

```bash
bash ~/zsvirt/gate-check.sh 192.168.122.123 <password>   # 登录 + 查询 vm-instances
bash ~/zsvirt/zs-query.sh 192.168.122.123 <password>     # 全资源快照
```

> GPU1 `~/zsvirt/` 下已积累一批现成脚本（gate-check / zs-query / zs-initN / 诊断脚本），可直接参考。

### 2.4 业务 VM 内运行的服务（10.100.0.181）

| 服务 | 端口 | 说明 |
|---|---|---|
| cAdvisor | 8080 | 容器指标，Prometheus 已抓取 |
| llama-server（llama.cpp + Qwen3.5-0.8B Q8_0） | 8081 | OpenAI 兼容 `/v1/chat/completions`；需 `"chat_template_kwargs":{"enable_thinking":false}` |
| agent-service | 8082 | `POST /task {"question":"..."}` 触发一次 Agent 任务 |
| Prometheus | 9090 | targets: cadvisor / llama-server / toxiproxy |
| Toxiproxy | 8474（API）/ 8666（代理 tool-service） | 故障注入 |
| tool-service | 仅 compose 内网 | 被 Toxiproxy 代理，宿主机无直接端口 |
| vm-agent | systemd 服务 `tracesphere-vm-agent` | 四探针事件 + PSI/cgroup 指标，JSON 行输出到 `/opt/tracesphere/evidence/vm-agent.log`（单次 <1% CPU、~12MB 内存） |
| 负载与脚本目录 | — | `/opt/tracesphere/workload/`、模型 `/opt/tracesphere/models/model.gguf` |

常用操作：

```bash
# 在业务 VM 上
cd /opt/tracesphere/workload
sudo docker compose ps
sudo docker compose up -d llama-server agent-service     # 拉起全栈
sudo docker logs agent-service --tail 20                 # 看 AppEvent 事件流
bash faults/run-task.sh "请用一句话介绍虚拟机可观测性"      # 端到端冒烟
bash faults/oom.sh ; bash faults/cpu.sh                  # 故障注入（内存/CPU）
bash faults/tool-failure.sh latency|timeout|down|reset|clear
```

### 2.5 ZSvirt 关键资源 UUID（B 直接可用）

| 资源 | UUID |
|---|---|
| Data Center（Datacenter-1） | `26fd04cdf31047e4a96aff5e41225420` |
| Cluster（Cluster-1） | `a29a9e1c13ac4017a187e30fca573625` |
| Host（host-1） | `cbb61d8a22cc4fd1b3702af673cbf405` |
| 数据存储（ps-local） | `4a0ecf3f472c4042aa4f9f9d36494b11` |
| 镜像存储（bs-local） | `2fa50ded127743859cf2bb80e9d3a25a` |
| 分布式交换机（dvs-ens2） | `db58a900bd344ba8ba6904ff7b7ce9e9` |
| 端口组（pg-demo，10.100.0.0/24） | `26391fe900e44409b3d2a37721b08f76` |
| 系统镜像（ubuntu-24.04-cloudimg） | `f39ba0991de143e6b76b0887e19edb0a` |
| 实例规格（off-small） | `21830e28a8f74391ba2a5fe46aca85af` |
| 业务 VM（workload-vm） | `63bbb4613a524e4e97090600af03da93` |
| 根卷（40 GiB） | `c6114309f9d34fa980a00a4895383654` |

---

## 3. 成员 B 开工指引（平台集成 / 数据模型 / 关联引擎）

### 3.1 第一优先级（W1）

1. **ZSvirt Adapter**：`RESTProvider` + `FixtureProvider`（同一 Domain Model）
   - RESTProvider：按 §2.3 登录并封装 `QueryVM / QueryHost / QueryZone / QueryImage / QueryL3Network` 等（真实字段以 API 返回为准）
   - FixtureProvider：把真实响应原样存 `fixtures/{vms,hosts,zones,images,...}.json`，配置 `zsvirt.provider=rest|fixture` 切换
2. **Resource Registry**：拉取 Host/VM 落 `resources` 表（SQLite WAL，索引：`timestamp / resource_id / correlation_id / event_type / cluster_id`）
3. **Agent Registration 接口**：`POST /api/v1/agents/register`（方案 §5.5），vm-agent 侧后续接
4. **Evidence Store**：定义 Event/Evidence 落库与查询（按 `correlation_id / resource_id / 时间窗`）

### 3.2 接口与数据源

- **ZSvirt 事件/告警**：`QueryAlarm / QueryEvent` 尚未实测，请优先验证并回填 API 路径与字段
- **Agent 事件**：`agent-service` 的 stdout（结构性 JSON，含 `task_id/correlation_id/event_type/attributes`），后续可加 HTTP 上报到 B 的 Event Ingest
- **系统事件**：`vm-agent` JSON 事件（exec/exit/oom/retransmit）——本地先落文件即可
- **Schema v1**：见方案 `方案初版.md` §5.4（字段冻结，不再改；如需扩展走 `schema_version`）

### 3.3 建议开发位置

- 代码：`tracesphere/platform/`（语言自定；建议 Python 快速迭代或 Go 与 vm-agent 一致）
- 联调即用：ZSvirt API（真实）+ VM 内负载（真实），无需自造演示数据

### 3.4 已知坑（必读，全部实测确认）

1. API 在 **8080**；登录密码字段传 **sha512 hex**；body 根键是 `logInByAccount`
2. `AddKVMHost` 端点是 `POST /hosts/kvm`；加主机可能需要 `--osinfo` 类似参数（本环境已建好，仅备查）
3. 本地主存储必须显式挂到集群（`POST /clusters/{clusterUuid}/primary-storage/{psUuid}`），否则调度报 `No available host found`
4. 创建 VM `strategy` 取值为 `InstantStart / JustCreate / CreateStopped`
5. `resizeRootVolume` API 本构建未暴露（扩盘走了离线 qemu-img + VolumeVO 同步）
6. 组件 action API 的 HTTP 方法混用（有的 PUT 有的 POST），失败时先试另一种方法
7. **时钟风险**：管理节点时间曾发生跳变，关联时间窗前请先做 clock skew 检查（方案 §5.5）

---

## 4. 成员 C 开工指引（诊断 / 告警 / 展示）

### 4.1 第一优先级（W1）

1. **Rule Engine 骨架**：加载 `rules/*.yaml`（格式见方案 §6.3），实现通用 Evidence Match 评分（`rule/evidence/correlation/result` 四段结构）
2. **三条规则**：`oom.yaml` / `cpu_contention.yaml` / `tool_failure.yaml`（模板可直接抄方案 §6.3）
3. **Web Console 脚手架**：React + TS + Ant Design + AntV G6 v5（拓扑）+ ECharts（曲线），四个页面占位：拓扑 / 健康 / 告警详情 / 诊断
4. **CLI**：`tracesphere topo|health|alerts|diagnose <resource>`

### 4.2 用 Fixture 解耦（不阻塞）

- B 的 Evidence Store 上线前，C 用 **fixture JSON** 开发：建议 `tracesphere/console/src/mocks/*.json`
- fixture 内容按 Schema v1 + Evidence/Diagnosis 结构（方案 §5.4、§6.3），B 完成后可无缝切换数据源
- 三条规则对应的证据样例（供 fixture 参考）：
  - **Case 1 OOM**：`memory.events.oom_kill` + `memory.current/max` + 容器重启 + `task.failed`
  - **Case 2 CPU**：PSI `cpu.some` + `cpu.stat.nr_throttled/throttled_usec` + llama P95/P99 + `task.failed(timeout)`
  - **Case 3 工具失败**：TCP 重传/连接失败（vm-agent 事件）+ tool 错误日志 + `tool.result(error)` + `task.failed`

### 4.3 数据源与联调

- 真实数据入口：Prometheus `10.100.0.181:9090`（指标查询 API 可直接用）、agent-service 事件流、vm-agent 事件
- B 的本地服务契约以 §5.4 Schema 为准；联调时 B 提供 `/api/v1/evidence?...` 这类只读接口即可
- 诊断验收标准见方案 §7（三个 Case 的 checklist）

---

## 5. 注意事项

1. **匿名化**：所有提交材料不得出现学校、指导教师等信息；本文件含凭据，仅内部使用
2. **资源纪律**：GPU1 为共享实验机，勿扰其他 VM/容器；业务 VM 盘 40 GiB，注意镜像/模型占用
3. **网络务实说明**：10.100.0.0/24 的 DHCP/NAT 目前由宿主机手工提供（dnsmasq + MASQUERADE），**ZSvirt 原生 flat DHCP 尚未生效**；不要执行无意义的 `reconnectHost`、删除 `pg-demo` 等操作，以免丢网
4. **改动服务前先记录**：`docker compose ps / logs` 留档；重启 vm-agent 前先保存事件输出样例
5. 每日开工先跑一次 §2.3 冒烟 + §2.4 `run-task.sh`，确认链路健康
