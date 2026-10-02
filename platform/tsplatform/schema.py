"""Schema v1 contract helpers (frozen in W1, see 方案 §5.4).

Accepted input forms for event ingest:

1. AppEvent (方案 §3.4)::

       {"event_type": "task.failed", "task_id": "...", "correlation_id": "...",
        "service": "agent-service", "timestamp": "...", "status": "timeout",
        "attributes": {...}}

2. Full Schema v1 event::

       {"schema_version": "v1", "origin": "cgroup", "mode": "real",
        "observed_at": "...", "type": "event", "resource_id": "...",
        "payload": {...}}

3. vm-agent loose event (exec/exit/oom/retransmit): any JSON object with an
   ``event_type`` / ``type``; unknown fields are preserved inside ``payload``.
"""

from typing import Any, Dict, List, Optional, Tuple

from .util import format_rfc3339, now_utc, parse_timestamp, safe_severity

SCHEMA_VERSION = "v1"

ORIGINS = ("zsvirt", "ebpf", "cgroup", "cadvisor", "app", "fluentbit", "gpu")
TYPES = ("resource", "metric", "event", "alert", "evidence", "diagnosis")
SEVERITIES = ("info", "warning", "major", "critical")

SCHEMA_FIELDS = (
    "schema_version",
    "origin",
    "mode",
    "observed_at",
    "ingested_at",
    "type",
    "resource_id",
    "correlation_id",
    "trace_id",
    "task_id",
    "severity",
    "payload",
    # platform extensions (denormalized for query / evidence matching)
    "event_type",
    "source",
    "cluster_id",
)

STATUS_SEVERITY = {
    "failed": "major",
    "failure": "major",
    "error": "major",
    "timeout": "major",
    "timed_out": "major",
    "warning": "warning",
    "warn": "warning",
    "degraded": "warning",
}

_ALERT_EVENT_HINTS = ("alarm", "alert")


class ValidationError(ValueError):
    """Raised when an event cannot be normalized into Schema v1."""


def _first_present(raw: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def normalize_event(
    raw: Dict[str, Any],
    default_origin: str = "app",
    default_mode: str = "real",
    default_source: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize a producer payload into a Schema v1 event row.

    Returns ``(event, warnings)``. Raises :class:`ValidationError` for
    non-object payloads or unusable timestamps.
    """
    if not isinstance(raw, dict):
        raise ValidationError("event must be a JSON object")

    warnings: List[str] = []

    schema_version = raw.get("schema_version") or SCHEMA_VERSION
    if schema_version != SCHEMA_VERSION:
        warnings.append("unknown schema_version=%s (stored as-is)" % schema_version)

    origin = raw.get("origin") or default_origin
    if origin not in ORIGINS:
        warnings.append("origin=%s not in %s" % (origin, list(ORIGINS)))

    mode = raw.get("mode") or default_mode
    if mode not in ("real", "mock"):
        warnings.append("mode=%s not in (real, mock)" % mode)
        mode = "mock"

    observed_raw = _first_present(raw, ("observed_at", "timestamp", "time", "ts", "occurred_at"))
    observed_dt = parse_timestamp(observed_raw)
    if observed_dt is None:
        observed_dt = now_utc()
        warnings.append("missing/unparseable observed_at, using ingest time")
    ingested_dt = parse_timestamp(raw.get("ingested_at")) or now_utc()

    event_type = _first_present(raw, ("event_type", "name", "kind"))
    payload: Dict[str, Any] = {}
    if isinstance(raw.get("payload"), dict):
        payload.update(raw["payload"])
    for key, value in raw.items():
        if key in SCHEMA_FIELDS:
            continue
        payload.setdefault(key, value)
    if event_type is None:
        event_type = payload.get("event_type")

    event_type = str(event_type) if event_type is not None else "unknown"

    declared_type = raw.get("type")
    if declared_type not in TYPES:
        if declared_type is not None:
            warnings.append("type=%s not in %s" % (declared_type, list(TYPES)))
        if isinstance(declared_type, str):
            etype = declared_type
        else:
            lowered = event_type.lower()
            etype = "alert" if any(h in lowered for h in _ALERT_EVENT_HINTS) else "event"
    else:
        etype = declared_type

    severity = safe_severity(raw.get("severity"))
    if severity is None:
        status = str(payload.get("status") or "").lower()
        severity = STATUS_SEVERITY.get(status)
    if raw.get("severity") is not None and severity is None:
        warnings.append("severity=%s not recognized" % raw.get("severity"))

    source = raw.get("source") or default_source or payload.get("service") or payload.get("component")

    event = {
        "schema_version": schema_version,
        "origin": origin,
        "mode": mode,
        "observed_at": format_rfc3339(observed_dt),
        "ingested_at": format_rfc3339(ingested_dt),
        "type": etype,
        "event_type": event_type,
        "resource_id": raw.get("resource_id"),
        "correlation_id": raw.get("correlation_id") or payload.get("correlation_id"),
        "trace_id": raw.get("trace_id") or payload.get("trace_id"),
        "task_id": raw.get("task_id") or payload.get("task_id"),
        "severity": severity,
        "source": source,
        "cluster_id": raw.get("cluster_id"),
        "payload": payload,
    }
    return event, warnings


def evidence_kind_for_origin(origin: Optional[str]) -> str:
    """Map a Schema v1 origin to an evidence kind used by RCA rule matching."""
    mapping = {
        "zsvirt": "zsvirt",
        "ebpf": "ebpf",
        "cgroup": "cgroup",
        "cadvisor": "metric",
        "app": "app_event",
        "fluentbit": "log",
        "gpu": "metric",
    }
    return mapping.get(origin or "", "other")
