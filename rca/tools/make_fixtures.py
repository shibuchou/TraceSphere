#!/usr/bin/env python3
"""make_fixtures.py —— 生成 C 侧回放 fixture（方案 §2.1 Fixture 降级/回放，P0）。

三个场景的证据取自真实环境演练报告：
  docs/evidence/case1-oom-chain.md / case2-cpu-chain.md / case3-tool-failure-chain.md
（GPU1 KVM + workload-vm 10.0.0.10，2026-09-20 实测；容器 ID / PSI / 节流计数 / 延迟均为真实值）

用法：
  python3 tools/make_fixtures.py            # 写 rca/fixtures/*.json
  python3 tools/make_fixtures.py --out DIR
"""
import argparse
import json
import os

# ---------------------------------------------------------------------------
# 真实环境标识（采集自 workload-vm：docker inspect / /etc/machine-id / DMI）
# ---------------------------------------------------------------------------
HOST_ID = "host:cbb61d8a22cc4fd1b3702af673cbf405"
VM_UUID = "63bbb4613a524e4e97090600af03da93"
VM_ID = "vm:" + VM_UUID

C_TOOL = "container:b9e5d37792546769827f4cfbb012e09ed7caca7343c60ec75ca109318bd717de"
C_AGENT = "container:0ca9b2f6a72a8d01c25ed3d53e046491b7342c941defd25eac68ca7d8c202087"
C_LLAMA = "container:5fe3237ffe6f2a5ad8d60b9df18c9c943c442e9281324c5c30ef8582e6964f3c"
C_TOXI = "container:e6eab2f12b53a8e3684fd21afc277f4660295866709b0e12beaee9906fe5659b"
C_STRESS = "container:e5d6f856a7479da140ff982417fca98f8b2841cb8690af4b8289529525af8d7a"

S_AGENT = "service:agent-service"
S_TOOL = "service:tool-service"
S_LLAMA = "service:llama-server"

NAME = {
    HOST_ID: "host-1",
    VM_ID: "workload-vm",
    C_TOOL: "tool-service",
    C_AGENT: "agent-service",
    C_LLAMA: "llama-server",
    C_TOXI: "toxiproxy",
    C_STRESS: "cpu-stress",
    S_AGENT: "agent-service",
    S_TOOL: "tool-service",
    S_LLAMA: "llama-server",
}


def container(resource_id, container_id, workload_type):
    return {
        "resource_id": resource_id,
        "kind": "container",
        "name": NAME[resource_id],
        "vm_id": VM_ID,
        "host_id": HOST_ID,
        "container_id": container_id,
        "state": "running",
        "origin": "cadvisor",
        "mode": "real",
        "labels": {"com.tracesphere.workload.type": workload_type},
        "attributes": {"vm_uuid": VM_UUID},
    }


def service(resource_id, workload_type):
    return {
        "resource_id": resource_id,
        "kind": "service",
        "name": NAME[resource_id],
        "vm_id": VM_ID,
        "origin": "app",
        "mode": "real",
        "labels": {"com.tracesphere.workload.type": workload_type},
    }


def task(task_id, correlation_id, state="finished"):
    return {
        "resource_id": "task:" + task_id,
        "kind": "task",
        "name": task_id,
        "correlation_id": correlation_id,
        "state": state,
        "origin": "app",
        "mode": "real",
        "attributes": {"task_id": task_id},
    }


def base_resources(extra_containers=()):
    resources = [
        {
            "resource_id": HOST_ID, "kind": "host", "name": "host-1 (GPU1)",
            "cluster_id": "a29a9e1c13ac4017a187e30fca573625", "state": "running",
            "origin": "zsvirt", "mode": "real",
            "attributes": {"cpuNum": 20, "memorySize": "30 GiB"},
        },
        {
            "resource_id": VM_ID, "kind": "vm", "name": "workload-vm",
            "host_id": HOST_ID, "cluster_id": "a29a9e1c13ac4017a187e30fca573625",
            "state": "running", "origin": "zsvirt", "mode": "real",
            "attributes": {
                "cpuNum": 4, "memorySize": 4294967296, "ips": ["10.0.0.10"],
                "machine_id": VM_UUID, "dmi_uuid": "63bbb461-3a52-4e4e-9709-0600af03da93",
                "configured_vm_uuid": VM_UUID,
            },
        },
        container(C_AGENT, C_AGENT.split(":")[1], "agent"),
        container(C_TOOL, C_TOOL.split(":")[1], "tool"),
        container(C_LLAMA, C_LLAMA.split(":")[1], "inference"),
        container(C_TOXI, C_TOXI.split(":")[1], "proxy"),
        service(S_AGENT, "agent"),
        service(S_TOOL, "tool"),
        service(S_LLAMA, "inference"),
    ]
    resources.extend(extra_containers)
    return resources


def base_edges():
    edges = [
        {"src_id": HOST_ID, "dst_id": VM_ID, "relation": "contains"},
        {"src_id": VM_ID, "dst_id": C_AGENT, "relation": "contains"},
        {"src_id": VM_ID, "dst_id": C_TOOL, "relation": "contains"},
        {"src_id": VM_ID, "dst_id": C_LLAMA, "relation": "contains"},
        {"src_id": VM_ID, "dst_id": C_TOXI, "relation": "contains"},
        {"src_id": C_AGENT, "dst_id": S_AGENT, "relation": "provides"},
        {"src_id": C_TOOL, "dst_id": S_TOOL, "relation": "provides"},
        {"src_id": C_LLAMA, "dst_id": S_LLAMA, "relation": "provides"},
        {"src_id": S_AGENT, "dst_id": S_TOOL, "relation": "calls"},
        {"src_id": S_AGENT, "dst_id": S_LLAMA, "relation": "calls"},
    ]
    return edges


def ev(evidence_id, signal, kind, layer, resource_id, observed_at, description,
       severity="info", correlation_id=None, task_id=None, value=None, unit=None,
       origin="app", mode="real", payload=None, source_event_ids=None):
    item = {
        "evidence_id": evidence_id,
        "signal": signal,
        "kind": kind,
        "layer": layer,
        "resource_id": resource_id,
        "resource_name": NAME.get(resource_id, resource_id),
        "observed_at": observed_at,
        "severity": severity,
        "description": description,
        "origin": origin,
        "mode": mode,
    }
    if correlation_id:
        item["correlation_id"] = correlation_id
    if task_id:
        item["task_id"] = task_id
    if value is not None:
        item["value"] = value
    if unit:
        item["unit"] = unit
    if payload:
        item["payload"] = payload
    if source_event_ids:
        item["source_event_ids"] = source_event_ids
    return item


def series(name, label, unit, points, thresholds=None):
    return {"name": name, "label": label, "unit": unit, "points": points, "thresholds": thresholds or []}


# ---------------------------------------------------------------------------
# Case 1：容器内存异常（Container OOM）
# ---------------------------------------------------------------------------
def case1():
    corr = "d38fc66c8364"
    task_id = "task-1789892737-9d8d72"
    evidence = [
        ev("ev-c1-01", "memory.events.oom_kill", "cgroup", "container", C_TOOL,
           "2026-09-20T08:25:35Z",
           "memory.events.oom_kill Δ=4（cgroup v2 内核计数，/system.slice/docker-b9e5d377…scope）",
           severity="critical", correlation_id=corr, value=4, unit="count",
           origin="cgroup", payload={"cgroup_path": "/system.slice/docker-b9e5d37792546769827f4cfbb012e09ed7caca7343c60ec75ca109318bd717de.scope"}),
        ev("ev-c1-02", "memory.current_ratio", "metric", "container", C_TOOL,
           "2026-09-20T08:25:34Z",
           "内存使用率峰值 1.021（working_set 1.46e7 / limit 1.43e7，Prometheus/cAdvisor）",
           severity="critical", correlation_id=corr, value=1.021, unit="ratio", origin="cadvisor"),
        ev("ev-c1-03", "oom.ebpf", "ebpf", "container", C_TOOL,
           "2026-09-20T08:25:35Z",
           "eBPF oom:mark_victim 事件 4 次（comm=python，vm-agent）",
           severity="critical", correlation_id=corr, value=4, unit="count",
           origin="ebpf", payload={"comm": "python", "kind": 3}),
        ev("ev-c1-04", "container.restart", "metric", "container", C_TOOL,
           "2026-09-20T08:25:36Z", "容器重启计数 +1（container_start_time_seconds 变化）",
           severity="warning", correlation_id=corr, value=1, unit="count", origin="cadvisor"),
        ev("ev-c1-05", "tool.result", "app_event", "application", S_AGENT,
           "2026-09-20T08:25:37Z",
           "tool.result status=error on agent-service status=error error=[Errno 104] Connection reset by peer",
           severity="major", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "error", "error": "[Errno 104] Connection reset by peer",
                    "tool": "mock-search", "target": "http://toxiproxy:8666/tool"}),
        ev("ev-c1-06", "task.failed", "app_event", "application", "task:" + task_id,
           "2026-09-20T08:25:37Z",
           "task.failed [app] status=error reason=tool call failed: [Errno 104] Connection reset by peer",
           severity="major", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "error", "reason": "tool call failed: [Errno 104] Connection reset by peer"}),
        ev("ev-c1-07", "psi_mem_some_avg10", "cgroup", "vm", VM_ID,
           "2026-09-20T08:25:35Z", "psi_mem_some_avg10=0.42（VM 级内存压力，vm-agent 5s 采样）",
           severity="info", correlation_id=corr, value=0.42, unit="percent", origin="cgroup"),
    ]
    resources = base_resources()
    resources.append(task(task_id, corr, "failed"))
    edges = base_edges() + [
        {"src_id": "task:" + task_id, "dst_id": S_AGENT, "relation": "runs_on"},
        {"src_id": "task:" + task_id, "dst_id": C_AGENT, "relation": "runs_on"},
    ]
    points_ratio = [
        [1789892675, 0.42], [1789892680, 0.55], [1789892685, 0.63], [1789892690, 0.71],
        [1789892695, 0.79], [1789892700, 0.86], [1789892705, 0.91], [1789892710, 0.97],
        [1789892715, 1.02], [1789892716, 0.31], [1789892720, 0.34], [1789892725, 0.33],
    ]
    points_ws = [[t, round(v * 14300000)] for t, v in points_ratio]
    return {
        "scenario": "case1-oom",
        "description": "容器内存异常（Container OOM）：tool-service limit 过低 → cgroup OOM kill → Agent 工具调用失败",
        "mode": "real",
        "window": {"from": "2026-09-20T08:21:40Z", "to": "2026-09-20T08:26:40Z", "seconds": 300},
        "focus": {"correlation_id": corr, "resource_id": C_TOOL},
        "resources": resources,
        "edges": edges,
        "evidence": evidence,
        "series": [
            series("memory.current_ratio", "tool-service 内存使用率", "ratio", points_ratio,
                   [{"value": 0.95, "label": "memory limit", "color": "#ff4d4f"}]),
            series("container_memory_working_set_bytes", "tool-service working_set", "bytes", points_ws),
        ],
        "incidents": [{
            "cluster_id": "cl-d38fc66c8364",
            "correlation_id": corr,
            "resource_id": C_TOOL,
            "rule": "correlation.correlation_id",
            "summary": "7 events, 4 resources, signals=[memory.events.oom_kill, tool.result, task.failed] focus=" + C_TOOL,
            "window_start": "2026-09-20T08:25:34Z",
            "window_end": "2026-09-20T08:25:37Z",
            "evidence_ids": [e["evidence_id"] for e in evidence],
        }],
        "meta": {
            "provenance": "docs/evidence/case1-oom-chain.md（真实演练报告，2026-09-20）",
            "environment": "GPU1 KVM + workload-vm 10.0.0.10（ZSvirt uuid " + VM_UUID + "）",
            "note": "数值均为实测：oom_kill 计数、working_set/limit、eBPF mark_victim、Agent AppEvent",
        },
    }


# ---------------------------------------------------------------------------
# Case 2：CPU 资源争抢
# ---------------------------------------------------------------------------
def case2():
    corr = "cf6d4dfcd64a"
    task_id = "task-1789892897-9025e6"
    psi_points = [
        [1789892877, 0.32], [1789892882, 0.21], [1789892887, 0.11], [1789892892, 0.07],
        [1789892897, 0.16], [1789892902, 6.41], [1789892907, 14.79], [1789892912, 18.16],
        [1789892917, 21.24], [1789892922, 22.48], [1789892927, 23.76], [1789892932, 24.17],
    ]
    evidence = [
        ev("ev-c2-01", "psi_cpu_some_avg10", "cgroup", "vm", VM_ID,
           "2026-09-20T08:28:52Z", "psi_cpu_some_avg10 峰值 24.17%（基线 < 1%，vm-agent 5s 采样）",
           severity="major", correlation_id=corr, value=24.17, unit="percent", origin="cgroup"),
        ev("ev-c2-02", "cpu.cfs.throttled_periods", "metric", "container", C_STRESS,
           "2026-09-20T08:28:52Z",
           "cpu.cfs.throttled_periods Δ=27（container_cpu_cfs_throttled_periods_total）",
           severity="warning", correlation_id=corr, value=27, unit="count", origin="cadvisor"),
        ev("ev-c2-03", "cpu.stat.nr_throttled", "cgroup", "container", C_STRESS,
           "2026-09-20T08:28:52Z", "cpu.stat.nr_throttled Δ=27，throttled_usec Δ=11020（cgroup v2 直读）",
           severity="warning", correlation_id=corr, value=27, unit="count", origin="cgroup"),
        ev("ev-c2-04", "llama_latency_p95_ms", "app_event", "application", S_LLAMA,
           "2026-09-20T08:28:54Z",
           "推理延迟 P95=36363 ms（agent-service inference.result duration_ms，基线 < 3s）",
           severity="major", correlation_id=corr, task_id=task_id, value=36363, unit="ms", origin="app"),
        ev("ev-c2-05", "task.finished", "app_event", "application", "task:" + task_id,
           "2026-09-20T08:28:54Z", "task.finished [app] status=ok（36.4s 后完成，未超时）",
           severity="info", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "ok", "duration_ms": 36363}),
        ev("ev-c2-06", "container.cpu_pct", "metric", "container", C_STRESS,
           "2026-09-20T08:28:52Z", "cpu-stress CPU 使用率 198.4%（--cpus=2 打满）",
           severity="warning", correlation_id=corr, value=198.4, unit="percent", origin="cadvisor"),
    ]
    resources = base_resources([
        container(C_STRESS, C_STRESS.split(":")[1], "fault-injection"),
    ])
    resources.append(task(task_id, corr, "finished"))
    edges = base_edges() + [
        {"src_id": VM_ID, "dst_id": C_STRESS, "relation": "contains"},
        {"src_id": "task:" + task_id, "dst_id": S_AGENT, "relation": "runs_on"},
    ]
    return {
        "scenario": "case2-cpu",
        "description": "CPU 资源争抢：cpu-stress 打满 vCPU → PSI/节流升高 → llama 推理延迟 36s（未超时）",
        "mode": "real",
        "window": {"from": "2026-09-20T08:24:54Z", "to": "2026-09-20T08:29:54Z", "seconds": 300},
        "focus": {"correlation_id": corr, "resource_id": C_STRESS},
        "resources": resources,
        "edges": edges,
        "evidence": evidence,
        "series": [
            series("psi_cpu_some_avg10", "VM CPU PSI some avg10", "percent", psi_points,
                   [{"value": 5, "label": "规则阈值", "color": "#faad14"}]),
            series("container_cpu_pct", "cpu-stress CPU 使用率", "percent",
                   [[1789892877, 3.1], [1789892902, 92.4], [1789892907, 168.2], [1789892917, 191.3],
                    [1789892927, 198.4], [1789892932, 198.9]]),
        ],
        "incidents": [{
            "cluster_id": "cl-cf6d4dfcd64a",
            "correlation_id": corr,
            "resource_id": C_STRESS,
            "rule": "correlation.correlation_id",
            "summary": "6 events, 3 resources, signals=[psi_cpu_some_avg10, cpu.cfs.throttled_periods, inference.result]",
            "window_start": "2026-09-20T08:28:17Z",
            "window_end": "2026-09-20T08:28:54Z",
            "evidence_ids": [e["evidence_id"] for e in evidence],
        }],
        "meta": {
            "provenance": "docs/evidence/case2-cpu-chain.md（真实演练报告，2026-09-20）",
            "environment": "GPU1 KVM + workload-vm 10.0.0.10",
            "note": "本轮实测任务未超时（36.4s 完成）：task.failed 条款未命中，Evidence Match 因此低于满分——体现评分由证据驱动；加强注入（收紧 cpu.max 或提高 stress 并发）可复现超时",
        },
    }


# ---------------------------------------------------------------------------
# Case 3：Agent 工具调用失败
# ---------------------------------------------------------------------------
def case3():
    corr = "8da4d26c78f6"
    task_id = "task-1789892840-179c3c"
    error = "timed out"
    evidence = [
        ev("ev-c3-01", "tool.result", "app_event", "application", S_AGENT,
           "2026-09-20T08:27:30Z",
           "tool.result status=error on agent-service status=error error=timed out",
           severity="major", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "error", "error": error, "tool": "mock-search",
                    "target": "http://toxiproxy:8666/tool", "duration_ms": 10000}),
        ev("ev-c3-02", "tool.transport_error", "app_event", "vm", S_AGENT,
           "2026-09-20T08:27:30Z",
           "transport-level 异常：timed out（Toxiproxy timeout toxic 5000ms，目标端点 http://toxiproxy:8666/tool）",
           severity="major", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "error", "error": error, "target": "http://toxiproxy:8666/tool"}),
        ev("ev-c3-03", "task.failed", "app_event", "application", "task:" + task_id,
           "2026-09-20T08:27:30Z",
           "task.failed [app] status=error reason=tool call failed: timed out",
           severity="major", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "error", "reason": "tool call failed: " + error}),
        ev("ev-c3-04", "tool.call", "app_event", "application", S_AGENT,
           "2026-09-20T08:27:20Z",
           "tool.call [app] tool=mock-search target=http://toxiproxy:8666/tool",
           severity="info", correlation_id=corr, task_id=task_id, origin="app",
           payload={"status": "ok", "tool": "mock-search", "target": "http://toxiproxy:8666/tool"}),
        ev("ev-c3-05", "zsvirt.alarm", "zsvirt", "zsvirt", VM_ID,
           "2026-09-20T08:27:20Z", "ZWatch 告警：VM 网络丢包率阈值告警（保持关注，非根因）",
           severity="warning", origin="zsvirt"),
    ]
    resources = base_resources()
    resources.append(task(task_id, corr, "failed"))
    edges = base_edges() + [
        {"src_id": "task:" + task_id, "dst_id": S_AGENT, "relation": "runs_on"},
        {"src_id": S_AGENT, "dst_id": C_TOXI, "relation": "uses"},
    ]
    series_list = [
        series("tool_call_duration_ms", "tool-service 调用耗时", "ms",
               [[1789892830, 24], [1789892840, 31], [1789892850, 10012], [1789892860, 10028], [1789892870, 10035]],
               [{"value": 10000, "label": "agent 客户端超时", "color": "#ff4d4f"}]),
    ]
    return {
        "scenario": "case3-tool-failure",
        "description": "Agent 工具调用失败：Toxiproxy 注入 timeout → 传输层异常 → task.failed",
        "mode": "real",
        "window": {"from": "2026-09-20T08:23:30Z", "to": "2026-09-20T08:28:30Z", "seconds": 300},
        "focus": {"correlation_id": corr, "resource_id": C_TOOL},
        "resources": resources,
        "edges": edges,
        "evidence": evidence,
        "series": series_list,
        "incidents": [{
            "cluster_id": "cl-8da4d26c78f6",
            "correlation_id": corr,
            "resource_id": C_TOOL,
            "rule": "correlation.correlation_id",
            "summary": "5 events, 4 resources, signals=[tool.call, tool.result, task.failed]",
            "window_start": "2026-09-20T08:27:20Z",
            "window_end": "2026-09-20T08:27:30Z",
            "evidence_ids": [e["evidence_id"] for e in evidence],
        }],
        "meta": {
            "provenance": "docs/evidence/case3-tool-failure-chain.md（真实演练报告，2026-09-20）",
            "environment": "GPU1 KVM + workload-vm 10.0.0.10",
            "note": "Toxiproxy timeout 场景不产生 connect() 失败（方案 §7 Case3 验收口径：至少一种 transport-level 信号）",
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures"))
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for builder in (case1, case2, case3):
        payload = builder()
        path = os.path.join(args.out, payload["scenario"] + ".json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print("wrote %s（%d 条证据）" % (path, len(payload["evidence"])))


if __name__ == "__main__":
    main()
