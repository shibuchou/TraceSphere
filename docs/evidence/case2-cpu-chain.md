# TraceSphere 证据链报告（interim）

- 生成时间：2026-09-20T08:28:54Z
- 时间窗：最近 4 分钟（08:24:54 ~ 08:28:54 UTC）
- 目标容器：`cpu-stress`
- correlation_id：`cf6d4dfcd64a`

## 1. vm-agent 内核事件 / PSI 指标
### 1.1 OOM / 网络异常事件
```json
{"comm":"python","kind":3,"origin":"oom","pid":155722,"ts":112607107364100,"wall":"2026-09-20T08:25:37Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155826,"ts":112607396637360,"wall":"2026-09-20T08:25:37Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155915,"ts":112607688510112,"wall":"2026-09-20T08:25:38Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155999,"ts":112608105537976,"wall":"2026-09-20T08:25:38Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156086,"ts":112608677355349,"wall":"2026-09-20T08:25:39Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156175,"ts":112609665215563,"wall":"2026-09-20T08:25:40Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156346,"ts":112611444697521,"wall":"2026-09-20T08:25:41Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156451,"ts":112614834691979,"wall":"2026-09-20T08:25:45Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156677,"ts":112621432484974,"wall":"2026-09-20T08:25:51Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156841,"ts":112634422251815,"wall":"2026-09-20T08:26:04Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157074,"ts":112643057875098,"wall":"2026-09-20T08:26:13Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157169,"ts":112643360859393,"wall":"2026-09-20T08:26:13Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157276,"ts":112643766961766,"wall":"2026-09-20T08:26:14Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157363,"ts":112644368917567,"wall":"2026-09-20T08:26:14Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157449,"ts":112645354506418,"wall":"2026-09-20T08:26:15Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157534,"ts":112647159170144,"wall":"2026-09-20T08:26:17Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157654,"ts":112650546343771,"wall":"2026-09-20T08:26:20Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157762,"ts":112657138849659,"wall":"2026-09-20T08:26:27Z"}
{"comm":"python","kind":3,"origin":"oom","pid":157873,"ts":112670120598667,"wall":"2026-09-20T08:26:40Z"}
{"comm":"llama-server","kind":3,"origin":"oom","pid":153917,"ts":112803737849567,"wall":"2026-09-20T08:28:54Z"}
```
### 1.2 进程事件（窗口内最后 15 条）
```json
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153953,"ts":112803803067149,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153953,"ts":112803803174719,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153953,"ts":112803803209310,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153953,"ts":112803803229953,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153953,"ts":112803803243343,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153953,"ts":112803803459333,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803803963415,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803803963553,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803803977362,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803805031841,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803805045663,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803805051473,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803805055704,"wall":"2026-09-20T08:28:54Z"}
{"comm":"docker-proxy","kind":2,"origin":"process","pid":153959,"ts":112803805160516,"wall":"2026-09-20T08:28:54Z"}
{"comm":"iptables","kind":1,"origin":"process","pid":158881,"ts":112803805498143,"wall":"2026-09-20T08:28:54Z"}
```
### 1.3 PSI / cgroup 指标（最近 12 条）
```json
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.32,"psi_io_some_avg10":0,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892877106689789,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.21,"psi_io_some_avg10":0,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892882105437215,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.11,"psi_io_some_avg10":0,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892887102334081,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.07,"psi_io_some_avg10":0,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892892105460232,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.16,"psi_io_some_avg10":0.24,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892897105443534,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":6.41,"psi_io_some_avg10":0.16,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892902107440564,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":14.79,"psi_io_some_avg10":0.08,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892907106433193,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":18.16,"psi_io_some_avg10":0.05,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892912106436370,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":21.24,"psi_io_some_avg10":0.03,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892917106428336,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":22.48,"psi_io_some_avg10":0.02,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892922101989892,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":23.76,"psi_io_some_avg10":0.01,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892927103427245,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":24.17,"psi_io_some_avg10":0,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892932106426280,"type":"metric"}
```

## 2. 容器 cgroup v2 证据（`cpu-stress`）

- cgroup 路径：`/sys/fs/cgroup/system.slice/docker-e5d6f856a7479da140ff982417fca98f8b2841cb8690af4b8289529525af8d7a.scope`（container_id=e5d6f856a747… pid=158699）
```text
--- memory.current ---
14925824
--- memory.max ---
max
--- memory.events ---
low 0
high 0
max 0
oom 0
oom_kill 0
oom_group_kill 0
--- cpu.stat ---
usage_usec 81495176
user_usec 81464204
system_usec 30972
core_sched.force_idle_usec 0
nr_periods 417
nr_throttled 27
throttled_usec 11020
nr_bursts 0
burst_usec 0
```

> **关键证据**：`memory.events.oom_kill = 0`（>0 表示该容器发生过 cgroup OOM 杀进程）

## 3. Prometheus / cAdvisor 指标（时间窗内）
container_memory_working_set_bytes (id): min=1.49e+07 max=1.49e+07 last=1.49e+07 (n=3)
cpu_cfs_throttled_periods_total (id): min=12 max=27 last=27 (n=3)
cpu_cfs_periods_total (id): min=87 max=389 last=389 (n=3)
container_start_time_seconds (id, 重启检测): min=1.79e+09 max=1.79e+09 last=1.79e+09 (n=3)

## 4. Agent 任务事件（agent-service 日志）
```json
{"event_type": "task.started", "task_id": "task-1789892897-9025e6", "correlation_id": "cf6d4dfcd64a", "service": "agent-service", "timestamp": "2026-09-20T08:28:17+0000", "status": "ok", "attributes": {"question": "CPU 争抢期间任务A"}}
{"event_type": "tool.call", "task_id": "task-1789892897-9025e6", "correlation_id": "cf6d4dfcd64a", "service": "agent-service", "timestamp": "2026-09-20T08:28:17+0000", "status": "ok", "attributes": {"tool": "mock-search", "target": "http://toxiproxy:8666/tool"}}
{"event_type": "tool.result", "task_id": "task-1789892897-9025e6", "correlation_id": "cf6d4dfcd64a", "service": "agent-service", "timestamp": "2026-09-20T08:28:17+0000", "status": "ok", "attributes": {"duration_ms": 1, "result": "{'tool': 'mock-search', 'query': 'CPU 争抢期间任务A', 'results': [{'title': 'VM 内可观测性实践', 'score': 0.91}, {'title': 'eBPF + cgroup 指标关联', 'score': 0.87}, {'title': 'Agent 任务轨迹追踪', 'score': 0.82}], 'latency_"}}
{"event_type": "inference.result", "task_id": "task-1789892897-9025e6", "correlation_id": "cf6d4dfcd64a", "service": "agent-service", "timestamp": "2026-09-20T08:28:54+0000", "status": "ok", "attributes": {"duration_ms": 36363}}
{"event_type": "task.finished", "task_id": "task-1789892897-9025e6", "correlation_id": "cf6d4dfcd64a", "service": "agent-service", "timestamp": "2026-09-20T08:28:54+0000", "status": "ok", "attributes": {"answer": "CPU 争抢期间，VM 内可观测性实践（VM 内可观测性实践）是最佳选择，因其能直接监控 CPU 负载与资源分配情况。"}}
```

## 5. 关联提示（供 RCA 使用）
- 把「时间窗内同时出现」的证据按发生时间排序，即可得到：
  1. 系统层信号（vm-agent/cgroup 指标）→ 2. 容器层状态（cgroup/Prometheus）→ 3. 应用层表现（Agent 事件）
- 若携带 `correlation_id`：应用层事件可直接串联；系统层事件按 `resource_id / 时间窗 / 容器身份` 关联
