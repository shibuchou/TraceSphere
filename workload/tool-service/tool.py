#!/usr/bin/env python3
"""TraceSphere tool-service

模拟外部工具服务（搜索/计算），仅标准库：
POST /tool {"query": "..."} -> {"tool": "mock-search", "results": [...]}
环境变量：
  TOOL_LATENCY_MS  固定延迟（毫秒），默认 0
"""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOL_LATENCY_MS = int(os.environ.get("TOOL_LATENCY_MS", "0"))
SERVICE = "tool-service"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._reply(200, {"status": "ok", "service": SERVICE})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/tool":
            self._reply(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            req = {}
        query = req.get("query", "")

        if TOOL_LATENCY_MS > 0:
            time.sleep(TOOL_LATENCY_MS / 1000.0)

        if query == "__fail__":
            self._reply(500, {"error": "simulated tool failure"})
            return

        self._reply(200, {
            "tool": "mock-search",
            "query": query,
            "results": [
                {"title": "VM 内可观测性实践", "score": 0.91},
                {"title": "eBPF + cgroup 指标关联", "score": 0.87},
                {"title": "Agent 任务轨迹追踪", "score": 0.82},
            ],
            "latency_ms": TOOL_LATENCY_MS,
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    print(f"{SERVICE} listening on :{port} latency_ms={TOOL_LATENCY_MS}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
