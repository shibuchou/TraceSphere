# TraceSphere 证据链报告（interim）

- 生成时间：2026-09-20T08:27:30Z
- 时间窗：最近 4 分钟（08:23:30 ~ 08:27:30 UTC）
- 目标容器：`toxiproxy`
- correlation_id：`8da4d26c78f6`

## 1. vm-agent 内核事件 / PSI 指标
### 1.1 OOM / 网络异常事件
```json
{"comm":"python","kind":3,"origin":"oom","pid":155597,"ts":112606118494987,"wall":"2026-09-20T08:25:36Z"}
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
```
### 1.2 进程事件（窗口内最后 15 条）
```json
{"comm":"date","kind":1,"origin":"process","pid":158388,"ts":112719764195904,"wall":"2026-09-20T08:27:30Z"}
{"comm":"date","kind":2,"origin":"process","pid":158388,"ts":112719764668665,"wall":"2026-09-20T08:27:30Z"}
{"comm":"grep","kind":1,"origin":"process","pid":158389,"ts":112719765073646,"wall":"2026-09-20T08:27:30Z"}
{"comm":"tail","kind":1,"origin":"process","pid":158392,"ts":112719765190926,"wall":"2026-09-20T08:27:30Z"}
{"comm":"awk","kind":1,"origin":"process","pid":158390,"ts":112719765210152,"wall":"2026-09-20T08:27:30Z"}
{"comm":"tee","kind":1,"origin":"process","pid":158393,"ts":112719765963531,"wall":"2026-09-20T08:27:30Z"}
{"comm":"grep","kind":1,"origin":"process","pid":158391,"ts":112719766241507,"wall":"2026-09-20T08:27:30Z"}
{"comm":"grep","kind":2,"origin":"process","pid":158389,"ts":112719772328280,"wall":"2026-09-20T08:27:30Z"}
{"comm":"awk","kind":2,"origin":"process","pid":158390,"ts":112719773041712,"wall":"2026-09-20T08:27:30Z"}
{"comm":"grep","kind":2,"origin":"process","pid":158391,"ts":112719773136743,"wall":"2026-09-20T08:27:30Z"}
{"comm":"tail","kind":2,"origin":"process","pid":158392,"ts":112719773149561,"wall":"2026-09-20T08:27:30Z"}
{"comm":"grep","kind":1,"origin":"process","pid":158394,"ts":112719773459354,"wall":"2026-09-20T08:27:30Z"}
{"comm":"grep","kind":1,"origin":"process","pid":158396,"ts":112719773686162,"wall":"2026-09-20T08:27:30Z"}
{"comm":"tail","kind":1,"origin":"process","pid":158397,"ts":112719773736507,"wall":"2026-09-20T08:27:30Z"}
{"comm":"awk","kind":1,"origin":"process","pid":158395,"ts":112719773803278,"wall":"2026-09-20T08:27:30Z"}
```
### 1.3 PSI / cgroup 指标（最近 12 条）
```json
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.93,"psi_io_some_avg10":0.57,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892792106318893,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.51,"psi_io_some_avg10":0.31,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892797106848727,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.52,"psi_io_some_avg10":0.39,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892802106227822,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.43,"psi_io_some_avg10":0.21,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892807107211992,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.29,"psi_io_some_avg10":0.14,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892812106475829,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.73,"psi_io_some_avg10":0.44,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892817106797177,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.63,"psi_io_some_avg10":0.29,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892822106334811,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.35,"psi_io_some_avg10":0.16,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892827107125983,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.41,"psi_io_some_avg10":0.1,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892832104084151,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.37,"psi_io_some_avg10":0.05,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892837102030282,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.25,"psi_io_some_avg10":0.03,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892842103026341,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.13,"psi_io_some_avg10":0.02,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892847106313578,"type":"metric"}
```

## 2. 容器 cgroup v2 证据（`toxiproxy`）

- cgroup 路径：`/sys/fs/cgroup/system.slice/docker-e6eab2f12b53a8e3684fd21afc277f4660295866709b0e12beaee9906fe5659b.scope`（container_id=e6eab2f12b53… pid=3463）
```text
--- memory.current ---
4304896
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
usage_usec 29692168
user_usec 11758690
system_usec 17933478
core_sched.force_idle_usec 0
nr_periods 0
nr_throttled 0
throttled_usec 0
nr_bursts 0
burst_usec 0
```

> **关键证据**：`memory.events.oom_kill = 0`（>0 表示该容器发生过 cgroup OOM 杀进程）

## 3. Prometheus / cAdvisor 指标（时间窗内）
container_memory_working_set_bytes (id): min=3.78e+06 max=4.31e+06 last=4.31e+06 (n=17)
cpu_cfs_throttled_periods_total (id): (no data)
cpu_cfs_periods_total (id): (no data)
container_start_time_seconds (id, 重启检测): min=1.79e+09 max=1.79e+09 last=1.79e+09 (n=17)

## 4. Agent 任务事件（agent-service 日志）
```json
{"event_type": "task.started", "task_id": "task-1789892840-179c3c", "correlation_id": "8da4d26c78f6", "service": "agent-service", "timestamp": "2026-09-20T08:27:20+0000", "status": "ok", "attributes": {"question": "工具故障演练任务 - 期望超时失败"}}
{"event_type": "tool.call", "task_id": "task-1789892840-179c3c", "correlation_id": "8da4d26c78f6", "service": "agent-service", "timestamp": "2026-09-20T08:27:20+0000", "status": "ok", "attributes": {"tool": "mock-search", "target": "http://toxiproxy:8666/tool"}}
{"event_type": "tool.result", "task_id": "task-1789892840-179c3c", "correlation_id": "8da4d26c78f6", "service": "agent-service", "timestamp": "2026-09-20T08:27:30+0000", "status": "error", "attributes": {"error": "timed out"}}
{"event_type": "task.failed", "task_id": "task-1789892840-179c3c", "correlation_id": "8da4d26c78f6", "service": "agent-service", "timestamp": "2026-09-20T08:27:30+0000", "status": "error", "attributes": {"reason": "tool call failed: timed out"}}
```

## 5. 关联提示（供 RCA 使用）
- 把「时间窗内同时出现」的证据按发生时间排序，即可得到：
  1. 系统层信号（vm-agent/cgroup 指标）→ 2. 容器层状态（cgroup/Prometheus）→ 3. 应用层表现（Agent 事件）
- 若携带 `correlation_id`：应用层事件可直接串联；系统层事件按 `resource_id / 时间窗 / 容器身份` 关联
