# C 侧真实环境验收记录（2026-09-21）

- 环境：GPU1（KVM 宿主机，20 vCPU / 30 GiB）+ ZSvirt 管理节点 + `workload-vm`（10.0.0.10，4 vCPU / 4 GiB）
- 链路：**真实注入 → VM 内真实采集 → platform 入库/关联 → C 侧 RCA 诊断**（全程无 mock）
- 数据源标注：`platform=real prometheus=real`（响应里可核验）
- 采集桥：`rca/tools/event-bridge.py`（VM 内，10s 轮询；A/B 正式接入后可下线）

## 汇总

| Case | 注入方式 | 真实观测到的关键证据 | Top-1 根因 | Evidence Match |
|---|---|---|---|---|
| Case 1 容器 OOM | `docker update --memory=8m tool-service` | 内核 OOM 日志 8 次（`oom_memcg=docker-505955ed…scope`）、容器重启 Δ=8、`task.failed` | **容器内存耗尽（Container OOM）** | 75/100 |
| Case 2 CPU 争抢 | `cpu-stress`（2 workers）+ `docker update --cpus=0.5 llama-server` | PSI `cpu.some` 峰值 40.9%、`cpu.cfs.throttled_periods` Δ=1190、推理任务 `timed out` | **CPU 资源争抢（CPU Resource Contention）** | 97/100 |
| Case 3 工具调用失败 | Toxiproxy `disable proxy tool`（服务不可达） | `tool.result` error（Connection refused）、`task.failed`、`tcp.retransmit` | **Agent 工具调用失败（Agent Tool Failure）** | 93/100 |

## Case 1 诊断输出（节选）

```text
数据源：platform=real prometheus=real ｜ 证据 49 条
[1] 容器内存耗尽（Container OOM）
    Evidence Match: 75/100 ｜ 规则 container_oom v1 ｜ 严重度 critical
      · 规则证据命中        47.1/55    3/5 条命中：memory.events.oom_kill、task.failed、container.restart
      · 时间优先性          0.0/15    task.failed 早于 memory.events.oom_kill 152.0s（时序不符）
      · 资源邻接度          8.0/10    2 条同属 container:505955ed…；4 条同 VM 内可关联
      · 信号强度          10.0/10    主证据 memory.events.oom_kill severity=critical
      · 独立证据数         10.0/10    覆盖 3 类证据来源：app_event / cgroup / metric
    证据（6 条，可溯源）：
      evt-36608f47   memory.events.oom_kill  cgroup  505955ed8594  02:52:03 value=8 count
      evt-361becb8   container.restart       metric  505955ed8594  02:52:07 value=8 count
```

> 评分不是满分，原因写在明细里：本轮 `task.failed` 早于 OOM（注入重试期间的历史失败），
> 时序维度判 0；`memory.current_ratio` 在 8 MiB limit 生效窗口内未被采样到。
> **这正是"证据驱动、可解释"的体现**——缺哪条证据，评分明细就显示缺哪条。

## Case 2 / Case 3 诊断输出（节选）

```text
[1] CPU 资源争抢（CPU Resource Contention）      Evidence Match: 97/100
      · 规则证据命中        55.0/55   4/5 条命中：psi_cpu_some_avg10、cpu.cfs.throttled_periods、llama_latency_p95_ms、task.failed
      · 资源邻接度          9.2/10    1 条同属 vm:a1b2c3d4…；5 条一跳邻接
      · 独立证据数         10.0/10    覆盖 3 类证据来源：app_event / cgroup / metric
      psi_cpu_some_avg10 峰值 40.9%（基线 < 1%） ｜ cpu.cfs.throttled_periods Δ=1190

[1] Agent 工具调用失败（Agent Tool Failure）      Evidence Match: 93/100
      · 规则证据命中        55.0/55   4/5 条命中：tool.result、task.failed、tcp.retransmit、tool.call
      · 时间优先性         15.0/15    task.failed 晚于 tool.result 0.0s
      · 独立证据数          5.0/10    覆盖 2 类证据来源：app_event / ebpf
      tool.result status=error（[Errno 111] Connection refused）
```

## 平台侧落库规模（Case 3 结束时）

```text
{'resources': 33, 'resource_edges': 32, 'events': 239, 'evidence': 239, 'clusters': 14, 'agents': 1}
```

## 复现命令

```bash
# 在 GPU1 上
bash ~/tracesphere/tools/demo-up.sh                    # platform + 采集桥 + 诊断服务/Console
bash ~/tracesphere/rca/bin/tracesphere alerts --window 10m
bash ~/tracesphere/rca/bin/tracesphere diagnose --correlation-id <corr> --window 10m
bash ~/tracesphere/rca/bin/tracesphere capture --scenario case1-oom \
     --correlation-id <corr> --window 10m --out fixtures   # 真实数据 → 回放 fixture
```

三个场景的实测证据已抓取为回放 fixture（`rca/fixtures/case1-oom.json` 等，含资源图、
证据、指标曲线、关联簇），断网或环境不可用时可直接 `--scenario` 回放（赛题可复现要求）。
