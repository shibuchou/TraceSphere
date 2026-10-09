# TraceSphere

> 面向 ZSvirt 虚拟机内容器与智能体工作负载的全栈可观测平台
> 第三届中国研究生操作系统开源创新大赛 · 智算云赛道 · ZSvirt 赛题

TraceSphere 以「**虚拟机为边界、工作负载为对象、事件关联为核心**」，统一组织指标、日志、事件与告警证据，
回答一个核心问题：**某个 Agent 任务的一次失败，究竟由应用、容器、虚拟机、GPU 还是宿主机引起？**

```text
         ZSvirt 基础设施（Host / VM / 网络 / 存储）            VM 内工作负载（真实）
        ┌─────────────────────────────────┐        ┌──────────────────────────────────┐
        │ RESTProvider（真实）             │        │ agent-service → tool-service     │
        │ FixtureProvider（回放/降级）     │        │               → llama-server     │
        │ Resource Registry + Resource Graph│        │ vm-agent（eBPF + PSI/cgroup）    │
        └──────────────┬──────────────────┘        │ cAdvisor / Prometheus            │
                       │                           └───────────────┬──────────────────┘
                       └───────────────┬───────────────────────────┘
                                       ▼
                  Platform（SQLite WAL：events / evidence / clusters）
                                       │
                  RCA Rule Engine（YAML 规则 + Evidence Match 评分）
                                       │
                  Web Console（React + G6 + ECharts） / CLI（tracesphere）
```

## 仓库结构（三成员合并）

```text
tracesphere/
├── vm-agent/        # A：VM 内探针（Go + cilium/ebpf + PSI/cgroup；systemd 安装/卸载）
├── workload/        # A：样例 AI 负载（agent-service / tool-service / llama.cpp / Toxiproxy / Prometheus / cAdvisor）
│   ├── faults/      #    故障注入脚本（OOM / CPU / 网络）
│   └── mock/        #    Mock DCGM 显存指标源（无 GPU 环境降级模式，赛题 §4）
├── platform/        # B：平台（Zsvirt 双 Provider、资源图、证据库、关联引擎、HTTP API）
├── rca/             # C：诊断（Rule Engine、四条规则、Evidence Match、CLI、fixture 回放）
├── console/         # C：Web Console（React + TS + AntD + G6 + ECharts）
├── deploy/          # 部署脚本（ZSvirt 环境 / VM 初始化 / systemd 服务）
├── tools/           # 集成工具（demo-up / acceptance / 四场景注入 / 证据链串联）
├── docs/            # 证据报告、方案说明、交接文档、修复记录（部分为内部资料，见下）
└── LICENSE          # MIT
```

## 最小化环境要求

| 项 | 要求 |
|---|---|
| 宿主机 | Linux x86_64（KVM + 嵌套虚拟化），20 vCPU / 30 GiB / 100 GiB 可用磁盘 |
| 虚拟化 | libvirt + qemu-kvm + virt-install（x86_64） |
| ZSvirt | v1.0.0 qcow2（x86_64，官方下载）；管理节点 8 vCPU / 8 GiB 起 |
| 业务 VM | Ubuntu 24.04（4 vCPU / 4 GiB / 40 GiB），Docker Engine + Compose |
| 平台侧 | Python 3.10+（零第三方依赖）、Node 22（仅构建 Console）、Go 1.25+（vm-agent）、Go 1.22+（RCA/CLI） |
| 无 GPU | 支持（CPU 推理 llama.cpp + Mock DCGM 为可选增强，不阻塞流程） |

第三方依赖（全部开源）：

| 组件 | 版本（实测） | 许可证 |
|---|---|---|
| llama.cpp（server 镜像） | latest | MIT |
| Qwen3.5-0.8B GGUF | Q8_0 | Apache-2.0 |
| Prometheus / cAdvisor | v2.53 / v0.49.1 | Apache-2.0 |
| Toxiproxy | latest | MIT |
| cilium/ebpf（Go） | v0.22.0 | MIT |
| AntV G6 / ECharts / React / AntD | 见 console/package.json | MIT |
| SQLite | 3.x（Python 内置） | Public Domain |

## 快速开始（从零部署）

### 1) 环境与凭据

```bash
export ZSVIRT_PASSWORD='<ZSvirt admin 密码>'            # 平台连接 ZSvirt 用
export TRACESPHERE_VM_UUID='<ZSvirt VM uuid>'           # workload-vm 的 uuid
export TRACESPHERE_VM_HOST='<业务 VM IP>'               # 例：10.0.0.10
export VM_PASSWORD='<业务 VM SSH 密码>'                 # ubuntu 用户
export TRACESPHERE_PLATFORM_URL='http://<平台 IP>:8000' # 业务 VM 可达的平台地址
```

> `tools/` 下的 demo-up / acceptance / case 脚本均从以上环境变量取部署参数，仓库内不含真实地址与口令。

> `deploy/README.md` 记录了本环境的 ZSvirt 部署、平台初始化与网络打通全过程（含踩坑）。

### 2) 平台侧（platform + rca 服务）

```bash
# 数据与配置
cp platform/config/platform.example.json platform/config/platform.json   # 按需修改
sudo install -d /etc/tracesphere
printf 'ZSVIRT_PASSWORD=%s\n' "$ZSVIRT_PASSWORD" | sudo tee /etc/tracesphere/platform.env

# 构建与启动（systemd 常驻）
cd rca && go build -o bin/tracesphere ./cmd/tracesphere && cd ..
cd console && npm ci && npm run build && cd ..
sudo bash deploy/systemd/install-services.sh
bash tools/demo-up.sh --status        # platform / rca / vm-agent 状态
# Console: http://<GPU1 IP>:8010/
```

### 3) 业务 VM 侧（探针 + 样例负载）

```bash
# vm-agent（eBPF + PSI/cgroup，systemd 化）
cd vm-agent && make build && cd ..
sudo bash vm-agent/deploy/install.sh vm-agent/bin/vm-agent
sudo tee /etc/tracesphere/agent.env >/dev/null <<EOF
VMAGENT_PLATFORM_URL=$TRACESPHERE_PLATFORM_URL
VMAGENT_VM_UUID=$TRACESPHERE_VM_UUID
VMAGENT_REPORT_PROCESS=0
EOF
sudo systemctl restart tracesphere-vm-agent

# 样例负载（docker compose）
cd /opt/tracesphere/workload
# 同目录 .env 注入 PLATFORM_EVENTS_URL / TRACESPHERE_VM_UUID（示例见 workload/.env.example）
sudo docker compose up -d
```

### 4) 冒烟验证

```bash
bash tools/demo-up.sh --status                    # 三件套状态
bash /opt/tracesphere/workload/faults/run-task.sh '你好'  # VM 内触发一次 Agent 任务（agent-service 直报）
curl -s http://127.0.0.1:8000/api/v1/health       # 平台：events 持续增长
cd rca && ./bin/tracesphere alerts --window 10m   # 告警/事件列表
```

## 四场景验收（真实注入 → 采集 → 关联 → 诊断）

```bash
# 先按 §1 导出环境变量（TRACESPHERE_VM_HOST / TRACESPHERE_VM_UUID / VM_PASSWORD / ZSVIRT_PASSWORD …）
bash tools/acceptance.sh
# 产出：/tmp/final/case{1,2,3}*.txt（RCA 诊断报告）+ rca/fixtures/*.json（真实回放数据）
```

| 场景 | 注入 | 期望结果 |
|---|---|---|
| Case 1 容器 OOM | tool-service memory limit 收紧 | 内核 OOM 证据 + 容器重启 + 任务失败 → Top-1「容器内存耗尽」**99/100** |
| Case 2 CPU 争抢 | cpu-stress + llama cpu.max 收紧 | PSI 升高 + 限流递增 + 推理超时 → Top-1「CPU 资源争抢」**85/100** |
| Case 3 工具调用失败 | Toxiproxy 关停工具代理 | 传输层异常 + tool.result error → Top-1「工具端点不可达」**67/100** |
| Case 4 GPU 显存耗尽（降级模式） | Mock DCGM `/inject mode=exhaust` | 显存占用率 > 90% + 耗尽事件 → Top-1「GPU 显存耗尽」**89/100** |

> Case 4 为无 GPU 硬件的降级演示（赛题 §4「模拟数据或最小化降级模式」）：平台需开启
> `TRACESPHERE_MOCK_GPU=1`（注册 `Host →contains→ GPU →assigned_to→ VM` 资源边），
> VM 内 `mock-dcgm` 容器上报模拟 DCGM 指标；真实环境替换为 DCGM exporter 后规则不变。

历史验收记录与证据链：`docs/evidence/`（三 Case 证据链报告、RCA 真实环境验收、探针开销实测）。

## 数据契约（W1 冻结）

- **Schema v1**：`schema_version / origin / mode / observed_at / ingested_at / type / event_type /
  resource_id / correlation_id / task_id / severity / source / cluster_id / payload`
- **资源模型**：Host → VM → Container → Process / Service → Task，关系词表见 `GET /api/v1/meta`
- **证据命名**：`rca/docs/API.md §1`（`memory.events.oom_kill` / `psi_cpu_some_avg10` / `task.failed` …）
- **诊断输出**：Evidence Match 0–100 分（**证据命中评分，非概率**），证据 ID 可逐条溯源

## ZSvirt 接口与权限声明

**平台侧调用（platform → ZSvirt，只读）**：

| 项 | 说明 |
|---|---|
| 登录接口 | `PUT /zstack/v1/accounts/login`（密码字段传 SHA-512 hex；会话 `Authorization: OAuth <sessionId>`，401/403 自动重登） |
| 资源查询 | `hosts` / `vm-instances` / `clusters` / `zones` / `images` / `l3-networks` / `l2-networks` / `l2-networks/port-groups` / `primary-storage` / `backup-storage` / `instance-offerings`（路径可在配置中覆盖） |
| 告警查询 | `zwatch/alarms`、`zwatch/events`（归一化为 Schema v1 告警事件） |
| 权限范围 | 仅使用一个账号做**只读查询**（inventory GET + 登录），不调用任何写接口；不修改 ZSvirt 资源 |
| 凭据管理 | 口令经 `ZSVIRT_PASSWORD` 环境变量注入（`/etc/tracesphere/platform.env`，权限 600），不入仓库、不落日志 |

**VM 内探针（vm-agent）**：

| 项 | 说明 |
|---|---|
| 运行身份 | systemd 常驻，默认 root（eBPF 加载与内核 journal 读取需要）；目标最小权限方案（`CAP_BPF + CAP_PERFMON`）见 `vm-agent/deploy/tracesphere-vm-agent.service` 注释 |
| 采集面 | cgroup v2 直读、PSI 文件、eBPF（exec/exit/网络重传，失败自动降级）、内核 OOM 日志模式匹配 |
| 卸载 | `sudo bash vm-agent/deploy/uninstall.sh`（停服务、删单元与二进制，保留证据目录） |

**端口暴露**（默认最小化）：platform 8000（**启用 `TRACESPHERE_API_TOKEN`**；非回环绑定未配置 token 时拒绝启动）、RCA + Console 8010（可启用 `TRACESPHERE_RCA_TOKEN`，写接口带最小限流）；VM 内 Prometheus / cAdvisor / llama / Toxiproxy / mock-dcgm / agent `/task` 默认只绑回环（跨机读取 Prometheus 用 `PROM_BIND`，Agent 任务可用 `TASK_TOKEN`）。

## 安全与脱敏

- **采集最小化**：事件为结构化字段（类型 / 资源 / 时间 / 严重级 / 结构化 payload），不采集容器完整 stdout 与业务请求体；内核日志仅做 OOM 模式匹配后上报结构化事件，原文不入库。
- **字段过滤**：平台 ingest 按 Schema v1 字段白名单归一化（`platform/tsplatform/schema.py`），未知字段统一收敛进 `payload`，不扩散为新列。
- **访问控制**：平台 API 静态令牌（`TRACESPHERE_API_TOKEN`，直报/注册链路已带 Bearer）；RCA 支持 `TRACESPHERE_RCA_TOKEN`；两边写接口均有每 IP 分钟级限流；工作负载控制面默认仅回环绑定。
- **隐私最小化**：agent-service 只上报结构化元数据（问题/回答仅上报长度，不上传原文），事件字段走 Schema v1 白名单。
- **提交脱敏**：`tools/sanitize-for-submission.sh` 生成提交包时排除内部资料并替换内网网段 / VM uuid / 口令字样，随后执行残留扫描（发现残留即失败退出）；清理记录见 `docs/anonymization-sweep-2026-09-21.md`。

## 内部资料与提交边界

> 大赛匿名化要求：提交材料不得出现学校、指导教师等可识别信息。

| 范围 | 文件 | 说明 |
|---|---|---|
| 可提交 | `vm-agent/ platform/ rca/ console/ workload/ tools/ deploy/systemd/` + 本 README + `docs/方案说明.md` + `docs/evidence/`（脱敏副本） | 已完成凭据/内网信息清理（脚本从环境变量取参）；证据报告由打包脚本统一替换内网网段 |
| 内部资料 | `docs/开工交接-*.md`、`docs/交接文档-*.md`、`docs/fixlog-*.md`、`docs/anonymization-sweep-*.md`、`docs/demo-*.md`、`deploy/README.md`、`deploy/zs-*.sh`、`deploy/mn-*.sh`、`deploy/*.exp`、`deploy/login-try.sh` | 含服务器/账号/内网信息，**不入提交物** |
| 需脱敏 | `platform/fixtures/`（ZSvirt 响应，含内网 UUID/IP） | 提交副本由打包脚本统一替换网段与 VM uuid（`192.0.2.0/24`、`10.0.0.0/24`） |

## 演示视频

4 分 30 秒演示（正常工作负载 → 四类故障注入 → 关联簇与证据链 → Top-1 根因与处置建议）：

- Gitee：https://gitee.com/shibuchou/TraceSphere/raw/main/docs/video/tracesphere-demo.mp4
- GitHub 镜像：https://github.com/shibuchou/TraceSphere/raw/main/docs/video/tracesphere-demo.mp4
- 文件与说明：`docs/video/`

## 许可

本项目代码以 MIT 许可证开源（见 `LICENSE`）；引用的开源组件遵循各自许可证（Prometheus / cAdvisor / Toxiproxy / llama.cpp / cilium-ebpf / AntV G6 / React / AntD 等，清单见上表）。Oracle/第三方商标归各自所有者。
