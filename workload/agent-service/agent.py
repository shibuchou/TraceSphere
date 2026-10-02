#!/usr/bin/env python3
"""TraceSphere agent-service

最小 Agent 任务编排服务（仅标准库，便于容器化与离线运行）：
POST /task {"question": "..."} ->
  1) tool.call  -> tool-service（经 Toxiproxy 代理）
  2) inference  -> llama-server（OpenAI 兼容接口）
  3) 全流程输出结构化 AppEvent（JSON 行，带 correlation_id / task_id）
"""
import json
import os
import re
import socket
import threading
import time
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOOL_URL = os.environ.get("TOOL_URL", "http://toxiproxy:8666/tool")
LLM_URL = os.environ.get("LLM_URL", "http://llama-server:8080/v1/chat/completions")
SERVICE = os.environ.get("SERVICE_NAME", "agent-service")
# 直报平台（为空则仅 stdout；生产由 vm-agent/agent-service 直报替换 event-bridge）
EVENTS_URL = os.environ.get("EVENTS_URL", "")
API_BASE = EVENTS_URL.rsplit("/events", 1)[0] if EVENTS_URL.endswith("/events") else ""
# ZSvirt VM uuid（部署方注入；用于资源图 VM->Container 归属）
VM_UUID = os.environ.get("VM_UUID", "")
# 平台 API Token（与 platform 的 TRACESPHERE_API_TOKEN 一致；设置后直报/注册带 Bearer）
PLATFORM_TOKEN = os.environ.get("PLATFORM_TOKEN", "")
# 任务接口令牌（可选；设置后 /task 需要 X-Task-Token，防控制面滥用）
TASK_TOKEN = os.environ.get("TASK_TOKEN", "")


def detect_container_id():
    """容器身份：优先 HOSTNAME（docker 默认 = 12 位短 ID），否则从 /proc/self/cgroup 提取。

    平台侧会把短 ID 前缀归一到完整 64 位 ID，与 cgroup/eBPF 采集使用同一容器资源。
    """
    hostname = os.environ.get("HOSTNAME", "")
    if re.fullmatch(r"[0-9a-f]{12}", hostname):
        return hostname
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as handle:
            for line in handle:
                if "docker-" in line:
                    return line.strip().split("docker-")[1].split(".scope")[0]
    except OSError:
        pass
    return ""


CONTAINER_ID = detect_container_id()


def platform_headers():
    headers = {"Content-Type": "application/json"}
    if PLATFORM_TOKEN:
        headers["Authorization"] = "Bearer " + PLATFORM_TOKEN
    return headers


def report(event):
    """异步直报平台 /api/v1/events（失败不影响任务执行，stdout 仍是完整日志）。"""
    if not EVENTS_URL:
        return

    def _post():
        try:
            req = urllib.request.Request(
                EVENTS_URL,
                data=json.dumps({"events": [event]}).encode(),
                headers=platform_headers(),
            )
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"event_type": "report.error", "error": str(exc)}), flush=True)

    threading.Thread(target=_post, daemon=True).start()


def register_agent():
    """启动时向平台注册本 VM 的 Agent 身份（替代 event-bridge 的 --register）。"""
    if not API_BASE or not VM_UUID:
        return

    def _post():
        payload = {
            "agent_id": "agent-service-%s" % VM_UUID[:12],
            "configured_vm_uuid": VM_UUID,
            "machine_id": "",
            "dmi_uuid": "",
            "hostname": socket.gethostname(),
            "ips": [],
            "version": "agent-service/1.0",
        }
        try:
            req = urllib.request.Request(
                API_BASE + "/agents/register",
                data=json.dumps(payload).encode(),
                headers=platform_headers(),
            )
            urllib.request.urlopen(req, timeout=5).read()
            print(json.dumps({"event_type": "agent.registered", "vm_uuid": VM_UUID}), flush=True)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"event_type": "report.error", "error": "register: %s" % exc}), flush=True)

    threading.Thread(target=_post, daemon=True).start()


def emit(event_type, task_id, correlation_id, status="ok", **attrs):
    ev = {
        "event_type": event_type,
        "task_id": task_id,
        "correlation_id": correlation_id,
        "service": SERVICE,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": status,
        "attributes": attrs,
    }
    if CONTAINER_ID:
        ev["container_id"] = CONTAINER_ID
    if VM_UUID:
        ev["vm_uuid"] = VM_UUID
    print(json.dumps(ev, ensure_ascii=False), flush=True)
    report(ev)


def http_json(url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


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
            self._reply(200, {"status": "ok"})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/task":
            self._reply(404, {"error": "not found"})
            return
        if TASK_TOKEN and (self.headers.get("X-Task-Token") or "") != TASK_TOKEN:
            self._reply(401, {"error": "missing or invalid task token"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            req = {}
        question = req.get("question", "请用一句话介绍虚拟机可观测性")
        task_id = f"task-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        corr = uuid.uuid4().hex[:12]

        # 隐私最小化：只上报结构化元数据，不上传问题/回答等业务文本（赛题 §4 敏感信息保护）
        emit("task.started", task_id, corr, question_len=len(question))

        # 1) 工具调用（经 Toxiproxy）
        tool_result = None
        try:
            emit("tool.call", task_id, corr, tool="mock-search", target=TOOL_URL)
            t0 = time.time()
            tool_result = http_json(TOOL_URL, {"query": question}, timeout=10)
            emit(
                "tool.result",
                task_id,
                corr,
                duration_ms=int((time.time() - t0) * 1000),
                result_len=len(json.dumps(tool_result, ensure_ascii=False)),
            )
        except Exception as e:  # noqa: BLE001
            emit("tool.result", task_id, corr, status="error", error=str(e))
            emit("task.failed", task_id, corr, status="error",
                 reason=f"tool call failed: {e}")
            self._reply(502, {"task_id": task_id, "correlation_id": corr,
                              "error": f"tool failed: {e}"})
            return

        # 2) 推理调用
        answer = ""
        try:
            t0 = time.time()
            llm = http_json(
                LLM_URL,
                {
                    "messages": [
                        {"role": "system",
                         "content": "你是 TraceSphere 演示助手，回答保持简洁。"},
                        {"role": "user",
                         "content": f"问题: {question}\n工具结果: {json.dumps(tool_result, ensure_ascii=False)}"},
                    ],
                    "max_tokens": 128,
                    "temperature": 0,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=120,
            )
            answer = (
                llm.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            emit("inference.result", task_id, corr,
                 duration_ms=int((time.time() - t0) * 1000))
        except Exception as e:  # noqa: BLE001
            emit("task.failed", task_id, corr, status="error",
                 reason=f"inference failed: {e}")
            self._reply(502, {"task_id": task_id, "correlation_id": corr,
                              "error": f"inference failed: {e}"})
            return

        emit("task.finished", task_id, corr, answer_len=len(answer))
        self._reply(200, {
            "task_id": task_id,
            "correlation_id": corr,
            "tool": tool_result,
            "answer": answer,
        })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"{SERVICE} listening on :{port}", flush=True)
    register_agent()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
