# TraceSphere 部署记录（W1 Environment Gate）

## 目标环境

| 项 | 值 |
|---|---|
| 部署主机 | x86_64 KVM 宿主机（20 vCPU / 30 GiB / 176 GiB 可用磁盘） |
| 嵌套虚拟化 | kvm_intel，nested=Y，/dev/kvm 可用 |
| libvirt | virsh / virt-install / qemu-img 已安装，default NAT 网络 active + autostart |
| ZSvirt 管理节点 VM | 12 vCPU / 16 GiB / virtio 磁盘 + host-passthrough CPU（qcow2 直接引导） |
| 管理节点地址 | <MN_IP>（libvirt NAT DHCP） |

## eBPF 能力实测（vm-agent 前置）

实测时间：2026-09-18，内核 7.0.0-31-generic

| 检查项 | 结果 |
|---|---|
| BTF | `/sys/kernel/btf/vmlinux` 存在 |
| perf_event_paranoid | 4（sudo 下 attach 正常） |
| `sched_process_exec` / `sched_process_exit` | tracepoint 存在，attach 成功 |
| `oom:mark_victim` | tracepoint 存在，attach 成功 |
| `tcp:tcp_retransmit_skb` | tracepoint 存在，attach 成功，实测捕获到真实重传事件 |
| tracefs | 已挂载（`/sys/kernel/tracing`） |

结论：目标内核支持 vm-agent 全部 4 个探针；当前无需降级采集模式。

## vm-agent 构建 / 运行验证

- 工具链：Go 1.22.2 + clang + bpftool + cilium/ebpf v0.22.0（GOPROXY=goproxy.cn）
- `make build` 一次通过：vmlinux.h（166,868 行）→ bpf2go → `bin/vm-agent`（5.7 MB）
- 运行验证：4 个探针 attach 成功，稳定输出 JSON 事件（exec / exit / OOM / retransmit），SIGTERM 优雅退出

## Environment Gate 结果（2026-09-19 00:33，通过 ✅）

| 检查项 | 结果 |
|---|---|
| ZSvirt 管理节点 VM | 运行中（嵌套 KVM） |
| MN 服务 | Running（Tomcat 8080 + UI 443） |
| REST 登录 | `PUT /accounts/login` → HTTP 200 + session uuid |
| 资源查询 | `GET /vm-instances`（OAuth session）→ HTTP 200 `{"inventories":[]}`（平台未初始化，符合预期） |

### 重要技术点（集成代码必须遵守）

1. **API 入口是 8080 端口**：`http://<MN>:8080/zstack/v1`；443 是 UI 的 nginx，只代理 `/download-helper`，不代理 `/zstack`。
2. **登录 password 字段传 SHA-512 哈希**（明文密码的 hex，不是明文）：`sha512(<password>)`；数据库 AccountVO.password 也是同一 sha512。
3. 初始 admin 密码未知（image 出厂密码非 `password`）：用 `zstack-ctl reset_password --password <new>` 重置后**需重启管理节点**（`zstack-ctl restart_node`）生效。
4. guest 内管理网卡默认 DOWN：控制台登录后 `ip link set ens2 up` + DHCP 获得地址（本环境为 <MN_IP>）。
5. 登录请求体结构：`{"logInByAccount":{"accountName":"admin","password":"<sha512>"}}`（注意不是 `logIn`）。
6. 认证后的请求头：`Authorization: OAuth <session-uuid>`。

## 当前进度

- [x] 部署脚本 `zsvirt-deploy.sh`（镜像校验 → libvirt 导入 → 12 vCPU / 16 GiB 启动，含 osinfo 兼容参数）
- [x] 镜像下载 + SHA256 校验通过
- [x] ZSvirt 控制台登录 + 管理服务启动（`zstack-ctl change_ip` / `zstack-ctl start`）
- [x] **REST API 登录 + 查询成功（Environment Gate 通过）**
- [x] ZSvirt 平台资源初始化（zone / cluster / host / 存储 / 网络 / 镜像 / 实例规格）
- [x] **业务 VM `workload-vm` 创建成功并运行**（4 vCPU / 4 GiB）
- [x] guest 网络打通（<VM_IP>，SSH 密码登录、外网、GPU1 路由直达）
- [x] 根盘扩容到 40 GiB（离线 qemu-img resize + VolumeVO 同步）
- [x] Docker + compose 插件 + registry 镜像加速（VM 内）
- [x] **vm-agent 在 ZSvirt VM 内运行（4 探针 attach 成功）**
- [x] **cAdvisor 部署（健康，1791 个 container_* 指标）**
- [x] **样例 AI 负载全链路跑通（agent-service → Toxiproxy → tool-service → llama-server/Qwen3.5-0.8B，CPU 推理返回中文答案）**
- [x] Prometheus + 四个抓取目标（cadvisor / llama-server / toxiproxy）+ 事件流（AppEvent 带 task_id/correlation_id）
- [x] 故障注入脚本就绪（OOM / CPU 压力 / Toxiproxy 网络故障）
- [x] **三个 Case 端到端演练完成**（注入 → 证据 → 关联）——详见下表
  报告：`tracesphere/docs/evidence/case{1,2,3}-*.md`；工具：`tracesphere/tools/`（evidence-chain.sh + run-case1/2/3.sh）
- [x] **探针 systemd 化 + 安装/卸载 + 开销实测**（`vm-agent/deploy/`；报告：`docs/evidence/vm-agent-overhead.md`，idle <1% CPU / 11MB，load 12MB；降级模式已验证）
- [ ] FixtureProvider（基于真实 REST Response 录制）
- [ ] 平台侧（Evidence Store / Correlation / Web Console）

### 三 Case 演练结果（2026-09-20）

| Case | 注入 | 观测证据 | 应用层结果 | 恢复 |
|---|---|---|---|---|
| 1. 容器 OOM | tool-service 内存上限 8MB | vm-agent OOM 事件 ×10（kind=3, comm=python）、Prometheus 内存曲线（0→14.6MB）、cgroup 证据 | `tool.result error: Connection reset by peer` → `task.failed`（correlation_id） | 解除限制 + force-recreate → 任务恢复正常 |
| 2. CPU 争抢 | cpu-stress（2 worker，cpus=2） | PSI `cpu.some` 0.2 → **24.17**、PSI `io.some` 同步上升、压力容器 cgroup cpu.stat | 任务耗时 **5.7s → 36.4s（约 6x）**；第二个任务因推理连接被关闭直接失败 | 停止压力 → 2.7s |
| 3. 工具调用故障 | Toxiproxy latency 12s | Toxiproxy cgroup/Prometheus 指标、PSI 曲线 | tool 调用 10s 超时 → `tool.result error: timed out` → `task.failed` | 清除 toxic → 任务恢复正常 |

> 关联方式：应用层按 `correlation_id` 串联；系统层按 `时间窗 + 容器身份（cgroup）+ resource_id` 关联。
> RCA 候选输出暂由证据报告“关联提示”承载，等 C 的 Rule Engine 上线后替换为结构化诊断。

### 环境打通记录（务实方案）

- **DHCP/NAT**：ZSvirt flat DHCP 在宿主机侧未下发（agent 仅收到 garp 调用，无 dhcp apply），为了不阻塞开发，采用务实方案：在管理节点 `br_dvs0_2344` 上配 10.100.0.2/24 + dnsmasq（DHCP 段 10.100.0.10-250，网关/DNS 指向 10.100.0.2）+ iptables MASQUERADE；后续再回填 ZSvirt 原生 DHCP。
- **VM 凭据**：VM 创建时 userdata 网络服务尚未启用，config drive 未生成；通过制作 NoCloud seed ISO（CIDATA 卷）挂载 cdrom → cloud-init 注入 ubuntu/root 密码（`<初始密码>`）→ SSH 可登录。
- **根盘扩容**：`resizeRootVolume` API 在本构建未暴露（PUT/POST 均无映射），改为离线 `qemu-img resize` 40G + 更新 `VolumeVO.size` + VM 内 growpart/resize2fs。
- **GPU1 直连 VM**：GPU1 加路由 `10.100.0.0/24 via <MN_IP>`，可用 sshpass 直达 <VM_IP>。

## ZSvirt 平台资源记录（2026-09-19）

| 资源 | UUID / 值 |
|---|---|
| Data Center | `26fd04cdf31047e4a96aff5e41225420`（Datacenter-1） |
| Cluster | `a29a9e1c13ac4017a187e30fca573625`（Cluster-1，KVM） |
| Host | `cbb61d8a22cc4fd1b3702af673cbf405`（host-1，管理节点自身，Connected） |
| 数据存储（LocalStorage） | `4a0ecf3f472c4042aa4f9f9d36494b11`（ps-local，已挂载集群） |
| 镜像存储（ImageStore） | `2fa50ded127743859cf2bb80e9d3a25a`（bs-local，已挂载数据中心） |
| 分布式交换机 | `db58a900bd344ba8ba6904ff7b7ce9e9`（dvs-ens2，LinuxBridge on ens2） |
| 端口组（L3） | `26391fe900e44409b3d2a37721b08f76`（pg-demo，VLAN 2344，IPAM+DHCP+Userdata） |
| IP 段 | 10.100.0.10 – 10.100.0.250，网关 10.100.0.1，DHCP 服务地址 10.100.0.2 |
| 系统镜像 | `f39ba0991de143e6b76b0887e19edb0a`（ubuntu-24.04-cloudimg） |
| 实例规格 | `21830e28a8f74391ba2a5fe46aca85af`（off-small，4 vCPU / 4 GiB） |
| 业务 VM | `63bbb4613a524e4e97090600af03da93`（workload-vm，Running） |

### 已知问题：guest 网络 DHCP 未下发（进行中）

- 现象：VM 网卡已接入 `br_dvs0_2344`（L2 通路正常），但宿主机侧 flat DHCP 服务未启动（无 dnsmasq / 未监听 67 端口），VM 未获取 IP。
- 已做：端口组已挂载 DHCP + Userdata 服务（Flat provider `a64965c0f7d54653a1fa7f7ae5d927b7`）；DHCP 服务地址已设为 10.100.0.2；reconnect host 已尝试。
- 待做：排查宿主机侧 kvmagent 的 flat DHCP 应用流程；兜底方案：通过 `virsh console`（VM 由 ZSvirt 在管理节点上以 libvirt 管理）在 VM 内配置静态 IP。
- 创建 VM 的一个前置坑（已解决）：本地数据存储必须显式挂载到集群（`POST /clusters/{clusterUuid}/primary-storage/{psUuid}`），否则调度器报 `No available host found`。

## 目录

| 文件 | 用途 |
|---|---|
| `zsvirt-deploy.sh` | ZSvirt 管理节点部署（Environment Gate） |
| `auto-deploy.sh` | 下载完成后的自动部署 watcher |
| `ebpf-capability-test.sh` | eBPF hook / 权限实测脚本 |
| `sendkeys.sh` | 无串口输出时向 guest 控制台逐字符输入（virsh send-key） |
| `zs-console-login.exp` / `zs-console-brute.exp` | expect 控制台交互（诊断用） |
| `gate-check.sh` | REST API 登录 + 查询验证（Environment Gate） |
| `login-try.sh` / `mn-*.sh` | 诊断脚本（密码探测 / DB 检查 / 账号核对，已完成使命） |
