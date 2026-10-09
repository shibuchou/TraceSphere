#!/usr/bin/env python3
"""event-bridge.py —— 把 VM 内的真实信号接入 TraceSphere Platform（legacy 应急回退）。

【已下线】2026-09-21 P0-2：vm-agent / agent-service 已实现直报（POST /api/v1/events），
本脚本不再参与主链路，保留用于"无直报能力"的旧 VM 应急回退。

为什么需要它（开工交接会记录）：
    A 的 vm-agent 只往 stdout 打 JSON 事件，agent-service 只往容器 stdout 打 AppEvent，
    两者都还没有 HTTP 上报；B 的 platform 已经提供 `POST /api/v1/events` 与
    `POST /api/v1/agents/register`。本脚本在**业务 VM 内**运行，把两路真实信号归一化后推送，
    使"注入 → 采集 → 入库 → 关联 → 诊断"的完整链路在 W1 即可跑通。
    A/B 正式接入后本脚本可直接下线（README 与开工交接均标注为临时接入桥）。

用法（在 workload-vm 上，需 sudo 以读取 docker 与 vm-agent 日志）：

    sudo python3 event-bridge.py --platform http://127.0.0.1:8000 \
        --vm-uuid a1b2c3d456784b7d8e9f0a1b2c3d4e5f --minutes 15 --register

    sudo python3 event-bridge.py ... --follow            # 持续跟随（演示模式）
    sudo python3 event-bridge.py ... --dry-run           # 只打印不推送
    sudo python3 event-bridge.py ... --include-process   # 连 exec/exit 也推（默认不推，噪声大）

信号归一化（对齐 rca/docs/API.md §1）：
    vm-agent oom(kind=3)   -> event_type=oom.ebpf          origin=ebpf    severity=critical
    vm-agent tcp(kind=4)   -> event_type=tcp.retransmit    origin=ebpf
    vm-agent cgroup metric -> event_type=cgroup.metric     origin=cgroup  （保留 psi_* 与 cgroup 样本）
    agent-service 日志     -> AppEvent 原样 + observed_at 规范化 + container_id 归属
    容器发现              -> event_type=container.discovered origin=cadvisor
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

VM_AGENT_LOG = "/opt/tracesphere/evidence/vm-agent.log"
AGENT_CONFIG = "/etc/tracesphere/agent.yaml"
BRIDGE_STATE = "/var/lib/tracesphere/bridge-state.json"

OOM_KIND = 3
TCP_KIND = 4
PROCESS_KINDS = (1, 2)


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def log(message):
    stamp = datetime.now().strftime("%H:%M:%S")
    print("[%s] %s" % (stamp, message), flush=True)


def run(cmd, timeout=20):
    try:
        out = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                             timeout=timeout, check=False)
        return out.stdout.decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        log("命令失败 %s: %s" % (cmd, exc))
        return ""


def rfc3339(value):
    """把多种真实格式的时间戳规范成 RFC3339（UTC）。

    真实来源里有：`2026-09-20T08:25:37+0000`（agent.py）、纳秒 epoch（vm-agent）、
    `2026-09-20T08:25:37Z`（vm-agent wall）。
    """
    if value is None or value == "":
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1e18:
            number /= 1e9
        elif number > 1e15:
            number /= 1e6
        elif number > 1e12:
            number /= 1e3
        return datetime.fromtimestamp(number, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value):
    try:
        return datetime.strptime(rfc3339(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


class Platform(object):
    def __init__(self, base_url, token="", dry_run=False):
        self.base = base_url.rstrip("/")
        self.token = token
        self.dry_run = dry_run
        self.posted = 0

    def get(self, path):
        if self.dry_run:
            return {}
        request = urllib.request.Request(self.base + path)
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except Exception as exc:  # noqa: BLE001
            log("GET %s 失败：%s" % (path, exc))
            return {}

    def post(self, path, payload):
        if self.dry_run:
            log("DRY-RUN POST %s %s" % (path, json.dumps(payload, ensure_ascii=False)[:300]))
            return {"dry_run": True}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=body,
                                         headers={"Content-Type": "application/json"})
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.loads(response.read().decode("utf-8") or "{}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:200]
                log("POST %s HTTP %s: %s" % (path, exc.code, detail))
                if exc.code < 500:
                    return {}
            except Exception as exc:  # noqa: BLE001
                log("POST %s 失败（第 %d 次）：%s" % (path, attempt + 1, exc))
            time.sleep(1.5 * (attempt + 1))
        return {}

    def post_events(self, events, chunk=200):
        sent = 0
        for start in range(0, len(events), chunk):
            batch = events[start:start + chunk]
            result = self.post("/api/v1/events", {"events": batch, "mode": "real"})
            sent += int(result.get("inserted") or 0)
            self.posted += len(batch)
        return sent


# ---------------------------------------------------------------------------
# 容器发现（让 platform 的资源图里有 Container/Service 节点）
# ---------------------------------------------------------------------------
def discover_containers(platform, vm_uuid):
    raw = run(["docker", "ps", "-q"])
    ids = [line.strip() for line in raw.splitlines() if line.strip()]
    if not ids:
        return {}
    raw = run(["docker", "inspect", "--format", "{{.Id}}\t{{.Name}}\t{{.State.Status}}"] + ids, timeout=30)
    events = []
    mapping = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        container_id = parts[0].strip()
        name = parts[1].strip().lstrip("/")
        status = parts[2].strip() if len(parts) > 2 else "running"
        mapping[name] = container_id
        events.append({
            "event_type": "container.discovered",
            "origin": "cadvisor",
            "mode": "real",
            "observed_at": now,
            "resource_id": "container:" + container_id,
            "container_id": container_id,
            "service": name,
            "status": status,
            "attributes": {"name": name, "vm_uuid": vm_uuid, "runtime": "docker"},
            "dedup_key": "container-discovered:" + container_id,
        })
    if events:
        platform.post_events(events)
        log("容器发现：%d 个（%s）" % (len(events), ", ".join(sorted(mapping))))
    return mapping


def register_agent(platform, vm_uuid, containers):
    machine_id = ""
    if os.path.exists("/etc/machine-id"):
        machine_id = open("/etc/machine-id").read().strip()
    dmi_uuid = ""
    for path in ("/sys/class/dmi/id/product_uuid", "/sys/class/dmi/id/board_serial"):
        if os.path.exists(path):
            try:
                dmi_uuid = open(path).read().strip()
                break
            except OSError:
                continue
    ips = []
    out = run(["hostname", "-I"])
    ips = [ip for ip in out.split() if not ip.startswith("127.")]
    payload = {
        "agent_id": "vm-agent-" + (machine_id[:8] or "unknown"),
        "configured_vm_uuid": vm_uuid,
        "machine_id": machine_id,
        "dmi_uuid": dmi_uuid,
        "hostname": run(["hostname"]).strip(),
        "ips": ips,
        "version": "event-bridge/1.0",
        "attributes": {"containers": sorted(containers)},
    }
    result = platform.post("/api/v1/agents/register", payload)
    log("Agent 注册：resource_id=%s ips=%s" % (result.get("resource_id"), ips))


# ---------------------------------------------------------------------------
# 容器 cgroup v2 采样（真实 OOM / 节流 / 内存比证据）
# ---------------------------------------------------------------------------
def read_text(path):
    try:
        with open(path, "r") as handle:
            return handle.read()
    except OSError:
        return ""


def cgroup_path_of(container_id):
    pid = run(["docker", "inspect", "-f", "{{.State.Pid}}", container_id]).strip()
    if pid and pid != "0":
        content = read_text("/proc/%s/cgroup" % pid)
        for line in content.splitlines():
            if line.startswith("0::"):
                return line.split("::", 1)[1].strip()
    return "/system.slice/docker-%s.scope" % container_id


def cgroup_value(path, key):
    for line in read_text(path).splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] == key:
            try:
                return int(fields[1])
            except ValueError:
                return None
    return None


def collect_container_cgroups(platform, containers):
    """按容器读 cgroup v2（memory.current/max、memory.events.oom_kill、cpu.stat）。

    为什么不用 cAdvisor 的 container_oom_events_total：本环境的 cAdvisor v0.49.1
    在该内核上并不暴露有效的 OOM 计数（实测恒为 0），而 cgroup v2 的
    memory.events.oom_kill 是内核权威计数（方案 §7 Case1 的主判据）。
    """
    root = "/sys/fs/cgroup"
    events = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, container_id in containers.items():
        path = root + cgroup_path_of(container_id)
        current = read_int(path + "/memory.current")
        limit = read_int(path + "/memory.max")
        sample = {
            "cgroup": path.replace(root, ""),
            "memory_current": current,
            "memory_max": 0 if limit >= (1 << 62) else limit,
            "oom_kills": read_key(path + "/memory.events", "oom_kill"),
            "nr_throttled": read_key(path + "/cpu.stat", "nr_throttled"),
            "throttled_usec": read_key(path + "/cpu.stat", "throttled_usec"),
        }
        severity = "info"
        if sample["memory_max"] and current / max(sample["memory_max"], 1) > 0.9:
            severity = "warning"
        events.append({
            "event_type": "cgroup.metric",
            "origin": "cgroup",
            "mode": "real",
            "observed_at": now,
            "resource_id": "container:" + container_id,
            "container_id": container_id,
            "service": name,
            "severity": severity,
            "source": "event-bridge",
            "payload": sample,
            "dedup_key": "cgroup-sample:%s:%s" % (container_id[:12], now),
        })
    if events:
        platform.post_events(events)
        log("cgroup 采样：%d 个容器" % len(events))
    return events


def read_int(path):
    text = read_text(path).strip()
    if text == "max":
        return 1 << 62
    try:
        return int(text)
    except ValueError:
        return 0


def read_key(path, key):
    value = cgroup_value(path, key)
    return value if value is not None else 0


# ---------------------------------------------------------------------------
# 内核 OOM 证据（唯一带容器归属的权威来源）
# ---------------------------------------------------------------------------
OOM_MEMCG_RE = re.compile(r"oom_memcg=/system\.slice/docker-([0-9a-f]{64})\.scope")
OOM_PID_RE = re.compile(r"\bpid=(\d+)")
OOM_TASK_RE = re.compile(r"\btask=([^,\s]+)")


def read_kernel_oom_events(platform, minutes):
    """解析内核 OOM 日志（journalctl -k -o json）。

    为什么必须用内核日志：本环境的 cAdvisor `container_oom_events_total` 恒为 0，
    而容器自身 cgroup 的 memory.events.oom_kill 在容器重启后归零；只有内核 OOM 记录
    同时提供**容器归属**（oom_memcg=/system.slice/docker-<id>.scope）、被杀进程与精确时间。
    这是方案 §7 Case1 主判据 `memory.events.oom_kill` 的真实来源。
    """
    raw = run(["journalctl", "-k", "-o", "json", "--since", "-%dm" % minutes, "--no-pager"], timeout=40)
    events = []
    seen = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("MESSAGE")
        if not isinstance(message, str):
            # journald 对含二进制字段的消息会返回数组
            if isinstance(message, list):
                message = " ".join(str(part) for part in message)
            else:
                continue
        if "oom_memcg=" not in message:
            continue
        match = OOM_MEMCG_RE.search(message)
        if not match:
            continue
        container_id = match.group(1)
        pid_match = OOM_PID_RE.search(message)
        pid = pid_match.group(1) if pid_match else "0"
        task_match = OOM_TASK_RE.search(message)
        task = task_match.group(1) if task_match else ""
        key = (container_id, pid)
        if key in seen:
            continue
        seen.add(key)
        stamp = entry.get("__REALTIME_TIMESTAMP")
        try:
            observed = datetime.fromtimestamp(int(stamp) / 1e6, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            observed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        events.append({
            "event_type": "memory.events.oom_kill",
            "origin": "cgroup",
            "mode": "real",
            "observed_at": observed,
            "resource_id": "container:" + container_id,
            "container_id": container_id,
            "severity": "critical",
            "source": "kernel",
            "value": 1,
            "attributes": {"pid": pid, "comm": task, "memcg": "docker-%s.scope" % container_id[:12]},
            "payload": {
                "delta": 1,
                "task": task,
                "pid": pid,
                "memcg": "docker-%s.scope" % container_id[:12],
                "evidence": "kernel oom-kill log (CONSTRAINT_MEMCG)",
            },
            "dedup_key": "kernel-oom:%s:%s" % (container_id[:12], pid),
        })
    if events:
        inserted = platform.post_events(events)
        log("内核 OOM：解析 %d 条（新入库 %d）" % (len(events), inserted))
    return events


# ---------------------------------------------------------------------------
# 容器 OOM / 重启检测（docker 视角的补充证据）
# ---------------------------------------------------------------------------
def load_state():
    if os.path.exists(BRIDGE_STATE):
        try:
            return json.load(open(BRIDGE_STATE))
        except ValueError:
            return {}
    return {}


def save_state(state):
    directory = os.path.dirname(BRIDGE_STATE)
    try:
        os.makedirs(directory, exist_ok=True)
        with open(BRIDGE_STATE, "w") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        log("状态写入失败（%s），OOM 检测将退化为首次基线" % exc)


def detect_oom_restarts(platform, containers):
    """对比 docker 容器状态，发现 OOM 杀进程 / 重启 → 产出内核级证据。

    docker inspect 的 State.OOMKilled 与 RestartCount 是宿主侧权威观测；
    cgroup 计数在容器重启后会归零，因此这里用状态差分补齐证据（Δt 精确到轮询间隔）。
    """
    state = load_state()
    events = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, container_id in containers.items():
        raw = run(["docker", "inspect", "-f",
                   "{{.RestartCount}}|{{.State.OOMKilled}}|{{.State.StartedAt}}|{{.State.Status}}", container_id])
        parts = raw.strip().split("|")
        if len(parts) < 4:
            continue
        try:
            restarts = int(parts[0])
        except ValueError:
            restarts = 0
        oom_killed = parts[1].strip() == "true"
        started_at = rfc3339(parts[2].strip())
        status = parts[3].strip()
        previous = state.get(container_id, {})
        delta = restarts - int(previous.get("restarts", restarts))
        if delta > 0 and previous:
            events.append({
                "event_type": "container.restart",
                "origin": "cadvisor",
                "mode": "real",
                "observed_at": now,
                "resource_id": "container:" + container_id,
                "container_id": container_id,
                "service": name,
                "severity": "warning",
                "source": "docker",
                "value": delta,
                "attributes": {"restart_count": restarts, "status": status},
                "payload": {"delta": delta, "restart_count": restarts, "oom_killed": oom_killed},
                "dedup_key": "container-restart:%s:%d" % (container_id[:12], restarts),
            })
            if oom_killed:
                events.append({
                    "event_type": "memory.events.oom_kill",
                    "origin": "cgroup",
                    "mode": "real",
                    "observed_at": now,
                    "resource_id": "container:" + container_id,
                    "container_id": container_id,
                    "service": name,
                    "severity": "critical",
                    "source": "docker",
                    "value": delta,
                    "attributes": {"oom_killed": True, "restart_count": restarts},
                    "payload": {"delta": delta, "oom_killed": True, "evidence": "docker State.OOMKilled + RestartCount"},
                    "dedup_key": "container-oomkill:%s:%d" % (container_id[:12], restarts),
                })
        state[container_id] = {"restarts": restarts, "oom_killed": oom_killed,
                               "started_at": started_at, "name": name, "updated_at": now}
    save_state(state)
    if events:
        platform.post_events(events)
        log("OOM/重启检测：产出 %d 条证据" % len(events))
    return events


# ---------------------------------------------------------------------------
# AppEvent（agent-service stdout）
# ---------------------------------------------------------------------------
def read_app_events(platform, minutes, container_id):
    raw = run(["docker", "logs", "agent-service", "--since", "%dm" % minutes], timeout=30)
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{") or '"event_type"' not in line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        observed = rfc3339(item.get("timestamp"))
        event = {
            "event_type": item.get("event_type"),
            "origin": "app",
            "mode": "real",
            "observed_at": observed,
            "task_id": item.get("task_id"),
            "correlation_id": item.get("correlation_id"),
            "service": item.get("service") or "agent-service",
            "source": "agent-service",
            "status": item.get("status"),
            "attributes": item.get("attributes") or {},
            "payload": {
                "status": item.get("status"),
                "attributes": item.get("attributes") or {},
            },
        }
        if container_id:
            event["container_id"] = container_id
        event["dedup_key"] = "appevent:" + hashlib.sha256(line.encode("utf-8")).hexdigest()[:32]
        # payload 里的关键字段提到顶层，便于 B 的 ingest 建立 service/task 资源
        for key in ("reason", "error", "duration_ms"):
            if key in (item.get("attributes") or {}):
                event["payload"][key] = item["attributes"][key]
        if item.get("status") and item["status"] != "ok":
            event["severity"] = "major"
        events.append(event)
    if events:
        inserted = platform.post_events(events)
        log("AppEvent：解析 %d 条（新入库 %d）" % (len(events), inserted))
    return events


# ---------------------------------------------------------------------------
# vm-agent（eBPF 事件 + PSI/cgroup 指标）
# ---------------------------------------------------------------------------
def tail_lines(path, max_lines):
    if not os.path.exists(path):
        log("vm-agent 日志不存在：%s" % path)
        return []
    size = os.path.getsize(path)
    block = 1 << 20
    data = b""
    with open(path, "rb") as handle:
        position = size
        while position > 0 and data.count(b"\n") <= max_lines:
            step = min(block, position)
            position -= step
            handle.seek(position)
            data = handle.read(step) + data
    return data.decode("utf-8", "replace").splitlines()[-max_lines:]


def read_vm_agent_events(platform, minutes, vm_uuid, include_process=False):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    lines = tail_lines(VM_AGENT_LOG, 60000)
    events = []
    stats = {"oom": 0, "tcp": 0, "metric": 0, "process": 0}
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        if '"origin":"process"' in line and not include_process:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        origin = item.get("origin")
        if origin == "cgroup" or item.get("type") == "metric":
            observed = parse_time(item.get("ts"))
            if observed < since:
                continue
            payload = {k: v for k, v in item.items() if k not in ("origin", "type", "ts")}
            severity = "info"
            psi_cpu = payload.get("psi_cpu_some_avg10")
            psi_mem = payload.get("psi_mem_some_avg10") or payload.get("psi_mem_full_avg10")
            if isinstance(psi_cpu, (int, float)) and psi_cpu > 5:
                severity = "warning"
            if isinstance(psi_mem, (int, float)) and psi_mem > 5:
                severity = "warning"
            events.append({
                "event_type": "cgroup.metric",
                "origin": "cgroup",
                "mode": "real",
                "observed_at": rfc3339(observed),
                "resource_id": "vm:" + vm_uuid if vm_uuid else None,
                "severity": severity,
                "source": "vm-agent",
                "payload": payload,
                "dedup_key": "vmagent-metric:%s" % item.get("ts"),
            })
            stats["metric"] += 1
            continue
        kind = item.get("kind")
        observed = parse_time(item.get("wall") or item.get("ts"))
        if observed < since:
            continue
        if kind == OOM_KIND:
            event_type, severity = "oom.ebpf", "critical"
            stats["oom"] += 1
        elif kind == TCP_KIND:
            event_type, severity = "tcp.retransmit", "warning"
            stats["tcp"] += 1
        elif kind in PROCESS_KINDS:
            event_type = "process.exec" if kind == 1 else "process.exit"
            severity = "info"
            stats["process"] += 1
        else:
            continue
        events.append({
            "event_type": event_type,
            "origin": "ebpf",
            "mode": "real",
            "observed_at": rfc3339(observed),
            "resource_id": "vm:" + vm_uuid if vm_uuid else None,
            "severity": severity,
            "source": "vm-agent",
            "attributes": {"comm": item.get("comm"), "pid": item.get("pid"), "kind": kind},
            "dedup_key": "vmagent:%s:%s:%s" % (item.get("origin"), item.get("ts"), item.get("pid")),
        })
    if events:
        inserted = platform.post_events(events)
        log("vm-agent：oom=%d tcp=%d metric=%d process=%d（新入库 %d）"
            % (stats["oom"], stats["tcp"], stats["metric"], stats["process"], inserted))
    return events


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def load_vm_uuid(args):
    if args.vm_uuid:
        return args.vm_uuid.strip()
    if os.path.exists(AGENT_CONFIG):
        try:
            for line in open(AGENT_CONFIG):
                if "vm_uuid" in line:
                    return line.split(":", 1)[1].strip().strip('"\'')
        except OSError:
            pass
    return os.environ.get("TRACESPHERE_VM_UUID", "")


def one_round(platform, args, vm_uuid, containers):
    if args.discover or not containers:
        containers = discover_containers(platform, vm_uuid)
    collect_container_cgroups(platform, containers)
    detect_oom_restarts(platform, containers)
    read_kernel_oom_events(platform, getattr(args, "oom_minutes", 5))
    read_app_events(platform, args.minutes, containers.get("agent-service"))
    read_vm_agent_events(platform, args.minutes, vm_uuid, args.include_process)
    return containers


def main():
    parser = argparse.ArgumentParser(description="TraceSphere VM 内信号接入桥（C 侧联调工具）")
    parser.add_argument("--platform", default=os.environ.get("TRACESPHERE_PLATFORM_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.environ.get("TRACESPHERE_PLATFORM_TOKEN", ""))
    parser.add_argument("--vm-uuid", default="", help="ZSvirt VM uuid（显式注入，不假定等于 DMI/machine-id）")
    parser.add_argument("--minutes", type=int, default=15, help="回看时间窗（分钟）")
    parser.add_argument("--oom-minutes", type=int, default=5,
                        help="内核 OOM 日志回看窗（分钟）；默认小于总窗口，避免把历史 OOM 重新灌入当前诊断")
    parser.add_argument("--follow", action="store_true", help="持续跟随（每 N 秒一轮）")
    parser.add_argument("--interval", type=int, default=15, help="follow 模式的轮询间隔（秒）")
    parser.add_argument("--register", action="store_true", help="启动时执行 Agent Registration")
    parser.add_argument("--discover", action="store_true", help="每轮重新发现容器")
    parser.add_argument("--include-process", action="store_true", help="同时上报 exec/exit 进程事件")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不推送")
    args = parser.parse_args()

    vm_uuid = load_vm_uuid(args)
    if not vm_uuid:
        log("警告：未提供 --vm-uuid，VM 级事件将不带 resource_id")
    platform = Platform(args.platform, args.token, args.dry_run)
    log("目标 platform=%s vm_uuid=%s dry_run=%s" % (args.platform, vm_uuid or "-", args.dry_run))

    health = platform.get("/api/v1/health")
    log("platform 健康：%s" % json.dumps(health, ensure_ascii=False)[:200])
    containers = discover_containers(platform, vm_uuid)
    if args.register:
        register_agent(platform, vm_uuid, containers)
    containers = one_round(platform, args, vm_uuid, containers)
    if not args.follow:
        log("完成：共提交 %d 条事件" % platform.posted)
        return 0
    log("进入跟随模式（每 %ds 一轮，Ctrl-C 退出）" % args.interval)
    try:
        while True:
            time.sleep(args.interval)
            containers = one_round(platform, args, vm_uuid, containers)
    except KeyboardInterrupt:
        log("退出：共提交 %d 条事件" % platform.posted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
