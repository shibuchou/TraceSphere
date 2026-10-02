#!/usr/bin/env python3
"""Mock DCGM：无 GPU 环境的模拟显存指标源（赛题 §4「模拟数据/最小化降级」）。

- 每 INTERVAL 秒把 ``gpu.metric`` 事件直报平台（origin=gpu, mode=mock）；
- 显存占用可注入：``POST /inject {"mode": "exhaust"|"normal"}``；
  exhaust 模式逐步逼近 100%，占用率越过 90% 时上报一次
  ``gpu.memory.exhausted``（severity=critical）；
- ``GET /metrics`` 输出 Prometheus 文本指标（prometheus.yml 已配置抓取）；
- ``GET /state`` 查看当前模拟状态。

仅使用 Python 标准库（与 tool-service / agent-service 相同镜像）。
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

PORT = int(os.environ.get("PORT", "9400"))
INTERVAL = float(os.environ.get("INTERVAL", "15"))
EVENTS_URL = os.environ.get("EVENTS_URL", "")
PLATFORM_TOKEN = os.environ.get("PLATFORM_TOKEN", "")
VM_UUID = os.environ.get("VM_UUID", "")
GPU_RESOURCE_ID = os.environ.get("GPU_RESOURCE_ID", "gpu:mock-gpu0")
MEM_TOTAL = int(os.environ.get("GPU_MEMORY_TOTAL_BYTES", str(8 * 1024 ** 3)))

_lock = threading.Lock()
_state = {
    "mode": "normal",
    "used_ratio": 0.18,
    "utilization_percent": 6.0,
    "temperature_c": 41.0,
    "exhausted_reported": False,
}


def _post(events):
    if not EVENTS_URL:
        return
    body = json.dumps({"events": events}).encode()
    headers = {"Content-Type": "application/json"}
    if PLATFORM_TOKEN:
        headers["Authorization"] = "Bearer " + PLATFORM_TOKEN
    req = Request(EVENTS_URL, data=body, headers=headers)
    try:
        urlopen(req, timeout=5).read()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"event_type": "report.error", "error": str(exc)}), flush=True)


def _base_event(event_type, **payload):
    payload["gpu_memory_total_bytes"] = MEM_TOTAL
    if VM_UUID:
        payload["vm_uuid"] = VM_UUID
    return {
        "event_type": event_type,
        "origin": "gpu",
        "mode": "mock",
        "resource_id": GPU_RESOURCE_ID,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "payload": payload,
    }


def _step():
    """推进一个采样周期并上报（注入后会被立即调用一次）。"""
    with _lock:
        if _state["mode"] == "exhaust":
            _state["used_ratio"] = min(0.995, _state["used_ratio"] + 0.16)
            _state["utilization_percent"] = min(99.0, _state["utilization_percent"] + 9)
            _state["temperature_c"] = min(88.0, _state["temperature_c"] + 3)
            exhausted = (
                _state["used_ratio"] >= 0.9 and not _state["exhausted_reported"]
            )
            if exhausted:
                _state["exhausted_reported"] = True
        else:
            _state["used_ratio"] = max(0.12, min(0.35, _state["used_ratio"] - 0.05 + 0.01))
            _state["utilization_percent"] = max(3.0, _state["utilization_percent"] - 6)
            _state["temperature_c"] = max(40.0, _state["temperature_c"] - 2)
            exhausted = False
        snapshot = dict(_state)

    payload = {
        "gpu_memory_used_ratio": round(snapshot["used_ratio"], 4),
        "gpu_memory_used_bytes": int(snapshot["used_ratio"] * MEM_TOTAL),
        "gpu_utilization_percent": round(snapshot["utilization_percent"], 2),
        "gpu_temperature_celsius": round(snapshot["temperature_c"], 1),
    }
    events = [_base_event("gpu.metric", **payload)]
    if exhausted:
        event = _base_event(
            "gpu.memory.exhausted",
            gpu_memory_used_ratio=payload["gpu_memory_used_ratio"],
            gpu_memory_used_bytes=payload["gpu_memory_used_bytes"],
        )
        event["severity"] = "critical"
        events.append(event)
    _post(events)


def _loop():
    while True:
        try:
            _step()
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"event_type": "report.error", "error": str(exc)}), flush=True)
        time.sleep(INTERVAL)


def _metrics_text():
    with _lock:
        snap = dict(_state)
    labels = 'resource_id="%s"' % GPU_RESOURCE_ID
    lines = [
        "# HELP ts_gpu_memory_used_ratio Mock GPU 显存占用率（0-1）",
        "# TYPE ts_gpu_memory_used_ratio gauge",
        "ts_gpu_memory_used_ratio{%s} %.4f" % (labels, snap["used_ratio"]),
        "# HELP ts_gpu_memory_used_bytes Mock GPU 显存占用字节",
        "# TYPE ts_gpu_memory_used_bytes gauge",
        "ts_gpu_memory_used_bytes{%s} %d" % (labels, int(snap["used_ratio"] * MEM_TOTAL)),
        "# HELP ts_gpu_memory_total_bytes Mock GPU 显存总量字节",
        "# TYPE ts_gpu_memory_total_bytes gauge",
        "ts_gpu_memory_total_bytes{%s} %d" % (labels, MEM_TOTAL),
        "# HELP ts_gpu_utilization_percent Mock GPU 利用率",
        "# TYPE ts_gpu_utilization_percent gauge",
        "ts_gpu_utilization_percent{%s} %.2f" % (labels, snap["utilization_percent"]),
        "# HELP ts_gpu_temperature_celsius Mock GPU 温度",
        "# TYPE ts_gpu_temperature_celsius gauge",
        "ts_gpu_temperature_celsius{%s} %.1f" % (labels, snap["temperature_c"]),
    ]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/metrics"):
            self._send(200, _metrics_text().encode(), "text/plain; version=0.0.4")
            return
        if self.path.startswith("/state"):
            with _lock:
                body = json.dumps(_state).encode()
            self._send(200, body)
            return
        self._send(404, json.dumps({"error": "not found"}).encode())

    def do_POST(self):
        if not self.path.startswith("/inject"):
            self._send(404, json.dumps({"error": "not found"}).encode())
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "invalid json"}).encode())
            return
        mode = str(body.get("mode") or "normal")
        if mode not in ("normal", "exhaust"):
            self._send(400, json.dumps({"error": "mode must be normal|exhaust"}).encode())
            return
        with _lock:
            _state["mode"] = mode
            if mode == "normal":
                _state["exhausted_reported"] = False
            else:
                # 注入后立刻逼近上限：保证演示/验收在数秒内即可复现耗尽（不等斜坡）
                _state["used_ratio"] = max(_state["used_ratio"], 0.9)
        _step()
        self._send(200, json.dumps({"mode": mode}).encode())


if __name__ == "__main__":
    threading.Thread(target=_loop, daemon=True).start()
    print(
        json.dumps(
            {
                "event_type": "mock_dcgm.started",
                "resource_id": GPU_RESOURCE_ID,
                "events_url": EVENTS_URL or "(stdout only)",
            }
        ),
        flush=True,
    )
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
