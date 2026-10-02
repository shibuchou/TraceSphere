# TraceSphere 证据链报告（interim）

- 生成时间：2026-09-20T08:25:40Z
- 时间窗：最近 4 分钟（08:21:40 ~ 08:25:40 UTC）
- 目标容器：`tool-service`
- correlation_id：`d38fc66c8364`

## 1. vm-agent 内核事件 / PSI 指标
### 1.1 OOM / 网络异常事件
```json
{"comm":"systemd","kind":3,"origin":"oom","pid":1,"ts":112543993882352,"wall":"2026-09-20T08:24:34Z"}
{"comm":"systemd","kind":3,"origin":"oom","pid":1,"ts":112604891833563,"wall":"2026-09-20T08:25:35Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155420,"ts":112605160535090,"wall":"2026-09-20T08:25:35Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155512,"ts":112605545761414,"wall":"2026-09-20T08:25:35Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155597,"ts":112606118494987,"wall":"2026-09-20T08:25:36Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155722,"ts":112607107364100,"wall":"2026-09-20T08:25:37Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155826,"ts":112607396637360,"wall":"2026-09-20T08:25:37Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155915,"ts":112607688510112,"wall":"2026-09-20T08:25:38Z"}
{"comm":"python","kind":3,"origin":"oom","pid":155999,"ts":112608105537976,"wall":"2026-09-20T08:25:38Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156086,"ts":112608677355349,"wall":"2026-09-20T08:25:39Z"}
{"comm":"python","kind":3,"origin":"oom","pid":156175,"ts":112609665215563,"wall":"2026-09-20T08:25:40Z"}
```
### 1.2 进程事件（窗口内最后 15 条）
```json
{"comm":"date","kind":1,"origin":"process","pid":156241,"ts":112610400919030,"wall":"2026-09-20T08:25:40Z"}
{"comm":"date","kind":2,"origin":"process","pid":156241,"ts":112610401386865,"wall":"2026-09-20T08:25:40Z"}
{"comm":"grep","kind":1,"origin":"process","pid":156242,"ts":112610401860490,"wall":"2026-09-20T08:25:40Z"}
{"comm":"awk","kind":1,"origin":"process","pid":156243,"ts":112610401879107,"wall":"2026-09-20T08:25:40Z"}
{"comm":"tail","kind":1,"origin":"process","pid":156245,"ts":112610402222771,"wall":"2026-09-20T08:25:40Z"}
{"comm":"grep","kind":1,"origin":"process","pid":156244,"ts":112610403147237,"wall":"2026-09-20T08:25:40Z"}
{"comm":"tee","kind":1,"origin":"process","pid":156246,"ts":112610403163047,"wall":"2026-09-20T08:25:40Z"}
{"comm":"grep","kind":2,"origin":"process","pid":156242,"ts":112610406943923,"wall":"2026-09-20T08:25:40Z"}
{"comm":"awk","kind":2,"origin":"process","pid":156243,"ts":112610408199211,"wall":"2026-09-20T08:25:40Z"}
{"comm":"grep","kind":2,"origin":"process","pid":156244,"ts":112610408282667,"wall":"2026-09-20T08:25:40Z"}
{"comm":"tail","kind":2,"origin":"process","pid":156245,"ts":112610408347057,"wall":"2026-09-20T08:25:40Z"}
{"comm":"grep","kind":1,"origin":"process","pid":156247,"ts":112610408763264,"wall":"2026-09-20T08:25:40Z"}
{"comm":"awk","kind":1,"origin":"process","pid":156248,"ts":112610408834029,"wall":"2026-09-20T08:25:40Z"}
{"comm":"tail","kind":1,"origin":"process","pid":156250,"ts":112610408859311,"wall":"2026-09-20T08:25:40Z"}
{"comm":"grep","kind":1,"origin":"process","pid":156249,"ts":112610408866617,"wall":"2026-09-20T08:25:40Z"}
```
### 1.3 PSI / cgroup 指标（最近 12 条）
```json
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.22,"psi_io_some_avg10":0.09,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892682107134738,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.12,"psi_io_some_avg10":0.05,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892687106559460,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.26,"psi_io_some_avg10":0.39,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892692105511307,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.41,"psi_io_some_avg10":0.33,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892697106168185,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.27,"psi_io_some_avg10":0.22,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892702102896413,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.15,"psi_io_some_avg10":0.12,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892707102197409,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.1,"psi_io_some_avg10":0.08,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892712107023545,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.2,"psi_io_some_avg10":0.04,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892717106949089,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.13,"psi_io_some_avg10":0.02,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892722106398540,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.25,"psi_io_some_avg10":0.01,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892727106542626,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.17,"psi_io_some_avg10":0.01,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892732106758866,"type":"metric"}
{"origin":"cgroup","psi_cpu_full_avg10":0,"psi_cpu_some_avg10":0.63,"psi_io_some_avg10":0.91,"psi_mem_full_avg10":0,"psi_mem_some_avg10":0,"ts":1789892737102698652,"type":"metric"}
```

## 2. 容器 cgroup v2 证据（`tool-service`）

- cgroup 路径：`/sys/fs/cgroup/system.slice/docker-7196bcad3bc14a641755cd8e19d6bdaca73a3d00b5ea5a30905124747fb3001b.scope`（container_id=7196bcad3bc1… pid=0）
```text
```

## 3. Prometheus / cAdvisor 指标（时间窗内）
container_memory_working_set_bytes (id): min=0 max=1.46e+07 last=1.01e+07 (n=17)
cpu_cfs_throttled_periods_total (id): (no data)
cpu_cfs_periods_total (id): (no data)
container_start_time_seconds (id, 重启检测): min=1.79e+09 max=1.79e+09 last=1.79e+09 (n=16)

## 4. Agent 任务事件（agent-service 日志）
```json
{"event_type": "task.started", "task_id": "task-1789892737-9d8d72", "correlation_id": "d38fc66c8364", "service": "agent-service", "timestamp": "2026-09-20T08:25:37+0000", "status": "ok", "attributes": {"question": "OOM 演练任务 - 期望工具调用失败"}}
{"event_type": "tool.call", "task_id": "task-1789892737-9d8d72", "correlation_id": "d38fc66c8364", "service": "agent-service", "timestamp": "2026-09-20T08:25:37+0000", "status": "ok", "attributes": {"tool": "mock-search", "target": "http://toxiproxy:8666/tool"}}
{"event_type": "tool.result", "task_id": "task-1789892737-9d8d72", "correlation_id": "d38fc66c8364", "service": "agent-service", "timestamp": "2026-09-20T08:25:37+0000", "status": "error", "attributes": {"error": "[Errno 104] Connection reset by peer"}}
{"event_type": "task.failed", "task_id": "task-1789892737-9d8d72", "correlation_id": "d38fc66c8364", "service": "agent-service", "timestamp": "2026-09-20T08:25:37+0000", "status": "error", "attributes": {"reason": "tool call failed: [Errno 104] Connection reset by peer"}}
```

## 5. 关联提示（供 RCA 使用）
- 把「时间窗内同时出现」的证据按发生时间排序，即可得到：
  1. 系统层信号（vm-agent/cgroup 指标）→ 2. 容器层状态（cgroup/Prometheus）→ 3. 应用层表现（Agent 事件）
- 若携带 `correlation_id`：应用层事件可直接串联；系统层事件按 `resource_id / 时间窗 / 容器身份` 关联
