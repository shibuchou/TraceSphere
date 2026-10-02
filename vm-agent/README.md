# vm-agent

TraceSphere VM 内轻量探针（成员 A）。设计目标：低侵入、单二进制、可一键安装/卸载、eBPF 不可用时自动降级。

## 采集能力

| 信号 | 实现 | 说明 |
|---|---|---|
| 进程 exec / exit | tracepoint `sched_process_exec` / `sched_process_exit` | 进程生命周期 |
| OOM Kill | tracepoint `oom:mark_victim` | 作为 cgroup `memory.events` 之外的增强证据 |
| TCP 重传 | tracepoint `tcp:tcp_retransmit_skb` | Case 3 网络异常证据 |
| cgroup v2 | `collector.ReadCgroup` | memory.current/max、oom_kill、cpu.stat（`VMAGENT_CGROUP` 指定路径） |
| PSI | `collector.ReadPSI` | `/proc/pressure/{cpu,memory,io}`，每 5s 一条指标 |

输出为 JSON 行（stdout → systemd 追加到日志文件），字段含 `origin / type / wall / ts / …`，
应用层事件另由 agent-service 输出 AppEvent（含 `task_id / correlation_id`）。

## 安装 / 卸载（systemd）

```bash
# 安装（幂等；二进制路径可省略，自动在 ./vm-agent、/tmp/vm-agent 等位置查找）
sudo bash deploy/install.sh [vm-agent 二进制路径]
systemctl status tracesphere-vm-agent

# 卸载（保留证据目录）
sudo bash deploy/uninstall.sh
# 彻底清理（含 /opt/tracesphere/evidence）
sudo bash deploy/uninstall.sh --purge
```

安装后布局：

| 路径 | 说明 |
|---|---|
| `/opt/tracesphere/bin/vm-agent` | 二进制 |
| `/etc/systemd/system/tracesphere-vm-agent.service` | systemd 单元 |
| `/opt/tracesphere/deploy/` | 部署文件固化（install/uninstall/measure/unit） |
| `/opt/tracesphere/evidence/vm-agent.log` | 事件与指标（JSON 行，供平台侧采集） |

## 构建（Linux, x86_64）

依赖：Go 1.22+、clang、bpftool、内核 BTF（`/sys/kernel/btf/vmlinux`）。

```bash
make build           # 生成 vmlinux.h + bpf2go + 编译
sudo ./bin/vm-agent  # 前台运行（调试用；生产用 systemd）
```

## 降级模式

eBPF 加载/attach 失败（权限、内核缺 tracepoint、memlock 限制等）时**自动降级**：
输出 `WARN ... 进入降级模式`，仅保留 PSI/cgroup 轮询采集，事件 Schema 不变。
已验证：非 root 运行时报 `remove memlock: operation not permitted` 并正常输出 PSI 指标。

## 权限说明

- 当前以 root 运行（systemd 服务默认）；
- 目标方案为最小权限 `CAP_BPF` + `CAP_PERFMON` + `CAP_SYS_RESOURCE`，
  单元文件中留有注释模板，具体 capability 集需按目标内核与 attach 类型实测确认；
- cgroup/PSI 采集只读，无需特权。

## 开销实测（2026-09-20，4 vCPU VM）

| 场景 | 平均 CPU | 最大 RSS |
|---|---|---|
| idle（30s） | < 1% | 11 MB |
| load（cpu-stress + 3 个推理任务，40s） | < 1% | 12 MB |

设计目标 CPU < 2% / 内存 < 100MB，实测显著优于目标。完整报告见
`docs/evidence/vm-agent-overhead.md`。
