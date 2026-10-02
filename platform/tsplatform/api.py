"""HTTP API for the TraceSphere platform (``/api/v1/*``), stdlib only.

Contract highlights (Schema v1, 方案 §5.4/§5.5):

- ``POST /api/v1/agents/register``     vm-agent VM identity binding
- ``POST /api/v1/events``              AppEvent / vm-agent / Schema v1 batch ingest
- ``GET  /api/v1/events``              query by correlation_id / resource_id / time window
- ``POST /api/v1/resources/sync``      pull ZSvirt provider -> registry -> graph
- ``GET  /api/v1/resources``           resource registry query
- ``GET  /api/v1/resources/{id}``      resource detail + edges
- ``GET  /api/v1/resources/{id}/graph``subgraph (Host -> VM -> Container -> Service -> Task)
- ``GET  /api/v1/evidence``            evidence store query (member C reads this)
- ``POST /api/v1/evidence``            manual evidence insert (tests / backfill)
- ``GET  /api/v1/clusters``            correlation clusters
- ``GET  /api/v1/clusters/{id}``       cluster + evidence + source events
- ``POST /api/v1/correlate``           run correlation over a time window
- ``GET  /api/v1/context``             aggregated RCA input (events + evidence + clusters + graph)
- ``GET  /api/v1/health``, ``GET /api/v1/meta``
"""

import datetime
import hmac
import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from . import SCHEMA_VERSION, __version__, domain
from .app import PlatformApp
from .schema import ORIGINS, SCHEMA_FIELDS, SEVERITIES, TYPES
from .util import format_rfc3339, now_utc, parse_timestamp

logger = logging.getLogger("tsplatform.api")

DEFAULT_CONTEXT_WINDOW_SECONDS = 900.0
DEFAULT_CORRELATE_HISTORY_SECONDS = 900.0


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


ROUTES = (
    ("GET", re.compile(r"^/api/v1/health$"), "health"),
    ("GET", re.compile(r"^/api/v1/meta$"), "meta"),
    ("POST", re.compile(r"^/api/v1/agents/register$"), "agents_register"),
    ("GET", re.compile(r"^/api/v1/agents$"), "agents_list"),
    ("POST", re.compile(r"^/api/v1/events$"), "events_post"),
    ("GET", re.compile(r"^/api/v1/events$"), "events_get"),
    ("POST", re.compile(r"^/api/v1/resources/sync$"), "resources_sync"),
    ("GET", re.compile(r"^/api/v1/resources$"), "resources_get"),
    ("GET", re.compile(r"^/api/v1/resources/(?P<resource_id>[^/]+)/graph$"), "resource_graph"),
    ("GET", re.compile(r"^/api/v1/resources/(?P<resource_id>[^/]+)$"), "resource_get"),
    ("POST", re.compile(r"^/api/v1/evidence$"), "evidence_post"),
    ("GET", re.compile(r"^/api/v1/evidence$"), "evidence_get"),
    ("GET", re.compile(r"^/api/v1/clusters$"), "clusters_get"),
    ("GET", re.compile(r"^/api/v1/clusters/(?P<cluster_id>[^/]+)$"), "cluster_get"),
    ("POST", re.compile(r"^/api/v1/correlate$"), "correlate_post"),
    ("GET", re.compile(r"^/api/v1/context$"), "context_get"),
)

ENDPOINT_DOC = [
    {"method": "GET", "path": "/api/v1/health"},
    {"method": "GET", "path": "/api/v1/meta"},
    {"method": "POST", "path": "/api/v1/agents/register"},
    {"method": "GET", "path": "/api/v1/agents"},
    {"method": "POST", "path": "/api/v1/events", "note": "single AppEvent, batch {events:[...]}, or Schema v1"},
    {"method": "GET", "path": "/api/v1/events", "params": ["correlation_id", "resource_id", "task_id", "event_type", "type", "severity", "cluster_id", "origin", "source", "from", "to", "order", "limit", "offset"]},
    {"method": "POST", "path": "/api/v1/resources/sync"},
    {"method": "GET", "path": "/api/v1/resources", "params": ["kind", "name", "cluster_id", "vm_id", "host_id", "state", "q", "limit", "offset"]},
    {"method": "GET", "path": "/api/v1/resources/{resource_id}"},
    {"method": "GET", "path": "/api/v1/resources/{resource_id}/graph", "params": ["depth", "direction"]},
    {"method": "POST", "path": "/api/v1/evidence"},
    {"method": "GET", "path": "/api/v1/evidence", "params": ["cluster_id", "correlation_id", "resource_id", "signal", "kind", "from", "to", "limit", "offset"]},
    {"method": "GET", "path": "/api/v1/clusters", "params": ["correlation_id", "resource_id", "rule", "status", "limit", "offset"]},
    {"method": "GET", "path": "/api/v1/clusters/{cluster_id}"},
    {"method": "POST", "path": "/api/v1/correlate", "body": {"from": "RFC3339", "to": "RFC3339", "resource_id": "optional", "correlation_id": "optional", "window_seconds": 5}},
    {"method": "GET", "path": "/api/v1/context", "params": ["correlation_id", "resource_id", "window_seconds", "from", "to"]},
]

RELATION_VOCABULARY = [
    domain.REL_CONTAINS,
    domain.REL_ASSIGNED_TO,
    domain.REL_ATTACHED_TO,
    domain.REL_USES,
    domain.REL_HAS_VOLUME,
    domain.REL_OVER,
    domain.REL_PROVIDES,
    domain.REL_RUNS_ON,
    domain.REL_CALLS,
    domain.REL_SPAWNS,
]


class TraceSphereHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "TraceSpherePlatform/%s" % __version__
    app: PlatformApp = None  # type: ignore

    # ----- plumbing -------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Token")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query, keep_blank_values=False)
        try:
            if not self._authorized(path):
                raise ApiError(401, "unauthorized", "missing or invalid API token")
            if method == "POST" and not self._post_rate_ok():
                raise ApiError(429, "rate_limited", "too many requests (see api.rate_limit_per_min)")
            name, params = self._resolve(method, path)
            handler = getattr(self, "_handle_" + name)
            result = handler(query, params)
            if isinstance(result, tuple):
                status, payload = result
            else:
                status, payload = 200, result
            self._send_json(status, payload)
        except ApiError as exc:
            self._send_json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        except ValueError as exc:
            self._send_json(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        except Exception as exc:  # noqa: BLE001
            logger.exception("unhandled error for %s %s", method, self.path)
            self._send_json(
                500,
                {"error": {"code": "internal_error", "message": "%s: %s" % (type(exc).__name__, exc)}},
            )

    def _resolve(self, method: str, path: str) -> Tuple[str, Dict[str, str]]:
        path_matched = False
        for route_method, pattern, name in ROUTES:
            match = pattern.match(path)
            if not match:
                continue
            path_matched = True
            if route_method == method:
                return name, match.groupdict()
        if path_matched:
            raise ApiError(405, "method_not_allowed", "%s not allowed on %s" % (method, path))
        raise ApiError(404, "not_found", "no route for %s" % path)

    def _authorized(self, path: str) -> bool:
        if path == "/api/v1/health" or self.command == "OPTIONS":
            return True
        token = (self.app.cfg.get("api") or {}).get("token")
        if not token:
            return True
        header = self.headers.get("Authorization") or ""
        supplied = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if not supplied:
            supplied = (self.headers.get("X-API-Token") or "").strip()
        return bool(supplied) and hmac.compare_digest(supplied, str(token))

    # 写接口最小限流（按客户端 IP 的每分钟令牌计；0 = 关闭）
    _rate_lock = threading.Lock()
    _rate_state: Dict[str, List[float]] = {}

    def _post_rate_ok(self) -> bool:
        limit = int((self.app.cfg.get("api") or {}).get("rate_limit_per_min") or 0)
        if limit <= 0:
            return True
        key = self.client_address[0]
        now = time.time()
        with TraceSphereHandler._rate_lock:
            hits = TraceSphereHandler._rate_state.setdefault(key, [])
            hits[:] = [t for t in hits if now - t < 60.0]
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        max_bytes = int((self.app.cfg.get("api") or {}).get("max_body_bytes") or 5 * 1024 * 1024)
        if length > max_bytes:
            raise ApiError(413, "payload_too_large", "body exceeds %d bytes" % max_bytes)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid_json", "request body must be valid UTF-8 JSON")
        if not isinstance(payload, dict):
            raise ApiError(400, "invalid_json", "request body must be a JSON object")
        return payload

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        allowed = (self.app.cfg.get("api") or {}).get("cors_origins") or ["*"]
        origin = self.headers.get("Origin")
        if "*" in allowed:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin and origin in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), fmt % args)

    # ----- handlers -------------------------------------------------------
    def _handle_health(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        status = self.app.status()
        status.update(
            {
                "status": "ok",
                "version": __version__,
                "schema_version": SCHEMA_VERSION,
                "time": format_rfc3339(now_utc()),
            }
        )
        return status

    def _handle_meta(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        return {
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "schema_fields": list(SCHEMA_FIELDS),
            "origins": list(ORIGINS),
            "types": list(TYPES),
            "severities": list(SEVERITIES),
            "resource_kinds": list(domain.RESOURCE_KINDS),
            "relations": RELATION_VOCABULARY,
            "endpoints": ENDPOINT_DOC,
            "provider": {"name": self.app.provider.name, "mode": self.app.provider.mode},
        }

    def _handle_agents_register(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        body = self._body()
        agent_id = body.get("agent_id")
        if not agent_id:
            raise ApiError(400, "invalid_request", "agent_id is required")
        ips = body.get("ips")
        if ips is not None and not isinstance(ips, list):
            raise ApiError(400, "invalid_request", "ips must be a list of strings")
        configured_vm_uuid = body.get("configured_vm_uuid")
        resource = None
        if configured_vm_uuid:
            resource = self.app.resources.get_by_uuid(str(configured_vm_uuid))
            if not resource:
                rid = domain.vm_id(str(configured_vm_uuid))
                self.app.resources.upsert(
                    {
                        "resource_id": rid,
                        "kind": domain.KIND_VM,
                        "name": body.get("hostname"),
                        "origin": "ebpf",
                        "mode": "real",
                        "labels": {"binding": "agent-registration"},
                        "attributes": {
                            "configured_vm_uuid": configured_vm_uuid,
                            "binding": "agent-registration",
                        },
                        "observed_at": format_rfc3339(now_utc()),
                    }
                )
                resource = self.app.resources.get(rid)
        now = format_rfc3339(now_utc())
        if resource:
            self.app.resources.upsert(
                {
                    "resource_id": resource["resource_id"],
                    "kind": resource["kind"],
                    "attributes": {
                        "agent_id": agent_id,
                        "machine_id": body.get("machine_id"),
                        "dmi_uuid": body.get("dmi_uuid"),
                        "hostname": body.get("hostname"),
                        "ips": ips or [],
                        "agent_registered_at": now,
                    },
                }
            )
        saved = self.app.agents.upsert(
            {
                "agent_id": agent_id,
                "resource_id": resource["resource_id"] if resource else None,
                "configured_vm_uuid": configured_vm_uuid,
                "machine_id": body.get("machine_id"),
                "dmi_uuid": body.get("dmi_uuid"),
                "hostname": body.get("hostname"),
                "ips": ips or [],
                "version": body.get("version"),
                "raw": body,
            }
        )
        vm = self.app.resources.get(saved["resource_id"]) if saved.get("resource_id") else None
        return {
            "agent_id": saved["agent_id"],
            "resource_id": saved.get("resource_id"),
            "registered_at": saved.get("registered_at"),
            "last_seen": saved.get("last_seen"),
            "vm": vm,
            "ingest": {"events_endpoint": "/api/v1/events", "schema_version": SCHEMA_VERSION},
        }

    def _handle_agents_list(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        agents = self.app.agents.list()
        return {"agents": agents, "count": len(agents)}

    def _handle_events_post(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        body = self._body()
        if isinstance(body.get("events"), list):
            items = body["events"]
            defaults = body
        else:
            items = [body]
            defaults = body
        if not items:
            raise ApiError(400, "invalid_request", "events must not be empty")
        origin = defaults.get("origin") or "app"
        mode = defaults.get("mode") or "real"
        source = defaults.get("source") or defaults.get("service")
        summary = self.app.ingest.ingest_many(
            items, default_origin=origin, default_mode=mode, default_source=source
        )
        return {
            "accepted": len(items),
            "inserted": summary["inserted"],
            "duplicates": summary["duplicates"],
            "event_ids": summary["event_ids"],
            "warnings": summary["warnings"],
        }

    def _handle_events_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        filters = {
            "resource_id": _q(query, "resource_id"),
            "correlation_id": _q(query, "correlation_id"),
            "task_id": _q(query, "task_id"),
            "event_type": _q(query, "event_type"),
            "type": _q(query, "type"),
            "severity": _q(query, "severity"),
            "cluster_id": _q(query, "cluster_id"),
            "origin": _q(query, "origin"),
            "source": _q(query, "source"),
        }
        from_ts = _ts(query, "from")
        to_ts = _ts(query, "to")
        limit = _int(query, "limit", 500, 1, 5000)
        offset = _int(query, "offset", 0, 0)
        order = _q(query, "order") or "asc"
        events = self.app.events.query(
            from_ts=from_ts, to_ts=to_ts, order=order, limit=limit, offset=offset, **filters
        )
        total = self.app.events.count(from_ts=from_ts, to_ts=to_ts, **filters)
        return {"events": events, "count": len(events), "total": total}

    def _handle_resources_sync(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        result = self.app.sync(ingest_events=True)
        return result.to_dict()

    def _handle_resources_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        filters = {
            "kind": _q(query, "kind"),
            "name": _q(query, "name"),
            "cluster_id": _q(query, "cluster_id"),
            "vm_id": _q(query, "vm_id"),
            "host_id": _q(query, "host_id"),
            "container_id": _q(query, "container_id"),
            "state": _q(query, "state"),
            "q": _q(query, "q"),
        }
        limit = _int(query, "limit", 200, 1, 2000)
        offset = _int(query, "offset", 0, 0)
        resources = self.app.resources.list(limit=limit, offset=offset, **filters)
        total = self.app.resources.count(**filters)
        return {"resources": resources, "count": len(resources), "total": total}

    def _handle_resource_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        resource_id = unquote(params["resource_id"])
        resource = self.app.resources.get(resource_id)
        if not resource:
            raise ApiError(404, "not_found", "resource %s not found" % resource_id)
        edges = self.app.resources.edges(resource_id, direction="both")
        return {"resource": resource, "edges": edges}

    def _handle_resource_graph(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        resource_id = unquote(params["resource_id"])
        if not self.app.resources.get(resource_id):
            raise ApiError(404, "not_found", "resource %s not found" % resource_id)
        depth = _int(query, "depth", 2, 1, 5)
        direction = _q(query, "direction") or "both"
        if direction not in ("in", "out", "both"):
            raise ApiError(400, "invalid_request", "direction must be in|out|both")
        return self.app.resources.subgraph(resource_id, depth=depth, direction=direction)

    def _handle_evidence_post(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        body = self._body()
        evidence_id, inserted = self.app.evidence.insert(body)
        return {
            "evidence_id": evidence_id,
            "inserted": inserted,
            "evidence": self.app.evidence.get(evidence_id),
        }

    def _handle_evidence_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        cluster_id = _q(query, "cluster_id")
        correlation_id = _q(query, "correlation_id")
        resource_id = _q(query, "resource_id")
        signal = _q(query, "signal")
        kind = _q(query, "kind")
        from_ts = _ts(query, "from")
        to_ts = _ts(query, "to")
        limit = _int(query, "limit", 500, 1, 5000)
        offset = _int(query, "offset", 0, 0)
        items = self.app.evidence.query(
            cluster_id=cluster_id,
            correlation_id=correlation_id,
            resource_id=resource_id,
            signal=signal,
            kind=kind,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            offset=offset,
            order=_q(query, "order") or "asc",
        )
        total = self.app.evidence.count(
            cluster_id=cluster_id,
            correlation_id=correlation_id,
            resource_id=resource_id,
            signal=signal,
            kind=kind,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        return {"evidence": items, "count": len(items), "total": total}

    def _handle_clusters_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        clusters = self.app.clusters.query(
            correlation_id=_q(query, "correlation_id"),
            resource_id=_q(query, "resource_id"),
            rule=_q(query, "rule"),
            status=_q(query, "status"),
            limit=_int(query, "limit", 200, 1, 2000),
            offset=_int(query, "offset", 0, 0),
        )
        for cluster in clusters:
            cluster["event_count"] = len(cluster.get("event_ids") or [])
            cluster["evidence_count"] = len(cluster.get("evidence_ids") or [])
        return {"clusters": clusters, "count": len(clusters)}

    def _handle_cluster_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        cluster_id = unquote(params["cluster_id"])
        cluster = self.app.clusters.get(cluster_id)
        if not cluster:
            raise ApiError(404, "not_found", "cluster %s not found" % cluster_id)
        evidence = self.app.evidence.query(cluster_id=cluster_id, limit=500)
        events = []
        for event_id in (cluster.get("event_ids") or [])[:500]:
            event = self.app.events.get(event_id)
            if event:
                events.append(event)
        cluster["event_count"] = len(cluster.get("event_ids") or [])
        cluster["evidence_count"] = len(cluster.get("evidence_ids") or [])
        return {"cluster": cluster, "evidence": evidence, "events": events}

    def _handle_correlate_post(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        body = self._body()
        from_ts = _normalize_ts(body.get("from"), "from")
        to_ts = _normalize_ts(body.get("to"), "to")
        if not from_ts:
            from_ts = format_rfc3339(now_utc() - datetime.timedelta(seconds=DEFAULT_CORRELATE_HISTORY_SECONDS))
        if not to_ts:
            to_ts = format_rfc3339(now_utc() + datetime.timedelta(seconds=60))
        window = body.get("window_seconds")
        try:
            window_value = float(window) if window is not None else None
        except (TypeError, ValueError):
            raise ApiError(400, "invalid_request", "window_seconds must be a number")
        return self.app.correlation.correlate(
            from_ts=from_ts,
            to_ts=to_ts,
            resource_id=body.get("resource_id"),
            correlation_id=body.get("correlation_id"),
            window_seconds=window_value,
        )

    def _handle_context_get(self, query: Dict[str, List[str]], params: Dict[str, str]) -> Dict[str, Any]:
        correlation_id = _q(query, "correlation_id")
        resource_id = _q(query, "resource_id")
        if not correlation_id and not resource_id:
            raise ApiError(400, "invalid_request", "correlation_id or resource_id is required")
        from_ts = _ts(query, "from")
        to_ts = _ts(query, "to")
        window = _int(query, "window_seconds", int(DEFAULT_CONTEXT_WINDOW_SECONDS), 1, 86400)
        if not from_ts and not to_ts:
            to_ts = format_rfc3339(now_utc() + datetime.timedelta(seconds=60))
            from_ts = format_rfc3339(now_utc() - datetime.timedelta(seconds=window))
        events = self.app.events.query(
            from_ts=from_ts, to_ts=to_ts, correlation_id=correlation_id, resource_id=resource_id,
            order="asc", limit=2000,
        )
        evidence = self.app.evidence.query(
            correlation_id=correlation_id,
            resource_id=resource_id,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=2000,
        )
        clusters = self.app.clusters.query(correlation_id=correlation_id, resource_id=resource_id, limit=100)
        graph = None
        if resource_id and self.app.resources.get(resource_id):
            graph = self.app.resources.subgraph(resource_id, depth=2, direction="both")
        resources: Dict[str, Dict[str, Any]] = {}
        for item in events + evidence:
            rid = item.get("resource_id")
            if rid and rid not in resources:
                resource = self.app.resources.get(rid)
                if resource:
                    resources[rid] = resource
        # window.seconds 由实际返回的 from/to 计算（RCA 侧按此对齐时间窗；缺失时为 0 曾导致误判）
        window_seconds_out = float(window)
        start_dt = parse_timestamp(from_ts)
        end_dt = parse_timestamp(to_ts)
        if start_dt and end_dt:
            window_seconds_out = max(0.0, (end_dt - start_dt).total_seconds())
        return {
            "correlation_id": correlation_id,
            "resource_id": resource_id,
            "window": {"from": from_ts, "to": to_ts, "seconds": window_seconds_out},
            "events": events,
            "evidence": evidence,
            "clusters": clusters,
            "resources": list(resources.values()),
            "graph": graph,
        }


def make_handler(app: PlatformApp):
    class _Handler(TraceSphereHandler):
        pass

    _Handler.app = app
    return _Handler


class PlatformHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(app: PlatformApp, host: str, port: int) -> PlatformHTTPServer:
    server = PlatformHTTPServer((host, int(port)), make_handler(app))
    logger.info(
        "TraceSphere platform listening on http://%s:%s (provider=%s/%s, schema=%s)",
        host,
        port,
        app.provider.name,
        app.provider.mode,
        SCHEMA_VERSION,
    )
    return server


# ----- query helpers ------------------------------------------------------
def _q(query: Dict[str, List[str]], name: str) -> Optional[str]:
    values = query.get(name)
    if not values:
        return None
    value = values[-1].strip()
    return value or None


def _int(query: Dict[str, List[str]], name: str, default: int, minimum: int = None, maximum: int = None) -> int:
    raw = _q(query, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, "invalid_request", "%s must be an integer" % name)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _ts(query: Dict[str, List[str]], name: str) -> Optional[str]:
    raw = _q(query, name)
    if raw is None:
        return None
    parsed = parse_timestamp(raw)
    if parsed is None:
        raise ApiError(400, "invalid_request", "%s must be RFC3339 (got %r)" % (name, raw))
    return format_rfc3339(parsed)


def _normalize_ts(value: Any, name: str) -> Optional[str]:
    if value is None or value == "":
        return None
    parsed = parse_timestamp(value)
    if parsed is None:
        raise ApiError(400, "invalid_request", "%s must be RFC3339" % name)
    return format_rfc3339(parsed)
