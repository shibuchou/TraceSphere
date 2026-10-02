# vm-agent 开销实测报告

> 环境：ZSvirt 业务 VM（workload-vm，4 vCPU / 4 GiB / Ubuntu 24.04 / 内核 6.8）
> 版本：vm-agent（Go + cilium/ebpf，ringbuf 1MiB × 3）
> 日期：2026-09-20 ｜ 成员 A

## 方法

- 采样：`deploy/measure-overhead.sh`，每 2s 读取 `/proc/<pid>/stat`（utime+stime）与 `/proc/<pid>/status`（VmRSS）
- CPU% = Δticks / HZ / Δt × 100（单核百分比，4 核机器上 1% ≈ 总 CPU 的 0.25%）
- 场景：
  1. **idle**：无业务负载，30s
  2. **load**：cpu-stress（2 个满载 worker，cpus=2）+ 3 个 Agent 任务（含 llama.cpp CPU 推理）并行，40s

## 结果

| 场景 | 样本数 | 平均 CPU | 最大 RSS |
|---|---|---|---|
| idle | 15 | **< 1%**（整数采样均为 0，偶发 1） | **11 MB** |
| load | 20 | **< 1%**（整数采样均为 0） | **12 MB** |

设计目标为 CPU < 2%、内存 < 100MB，实测**显著优于目标**。

## 优化记录

- 初版 3 个 ringbuf 各 16MiB（mmap 计入 RSS），实测 RSS ~103MB；
- 调整为 1MiB × 3 后 RSS 降至 **11MB**（事件速率远低于阈值，不影响采集完整性）。

## 权限与降级

- 当前以 root 运行（systemd 服务 `tracesphere-vm-agent.service`）；
- 目标方案为最小权限（`CAP_BPF` + `CAP_PERFMON` + `CAP_SYS_RESOURCE`），单元文件中已给出注释模板，需按目标内核/attach 类型实测确认；
- **降级模式已验证**：非 root 运行（无权限设置 memlock）时自动输出
  `WARN eBPF 探针不可用（remove memlock: ... operation not permitted），进入降级模式`
  并继续输出 PSI/cgroup 指标（实测 PSI 数据正常）。

## 安装 / 卸载

```bash
# 安装（二进制 + systemd 服务，幂等可重复执行）
sudo bash deploy/install.sh /path/to/vm-agent
systemctl status tracesphere-vm-agent

# 卸载（保留证据目录；--purge 一并清理）
sudo bash deploy/uninstall.sh
sudo bash deploy/uninstall.sh --purge
```

部署文件会固化到 `/opt/tracesphere/deploy/`（install/uninstall/measure/unit 四件套），
运行时数据：
- 二进制：`/opt/tracesphere/bin/vm-agent`
- 事件与指标：`/opt/tracesphere/evidence/vm-agent.log`（JSON 行，供平台侧 Event Ingest / evidence-chain.sh 读取）
