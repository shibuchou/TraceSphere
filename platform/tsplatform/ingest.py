"""Event ingest: Schema v1 normalization + identity enrichment (方案 §5.5).

Application-layer events carry ``correlation_id`` / ``task_id``; system-layer
events (cgroup / eBPF / cAdvisor) carry a ``resource_id``. This module maps
loose producer payloads onto the same identity model and lazily materializes
Service / Task / Container resources so the correlation engine can use the
resource graph immediately.
"""

from typing import Any, Dict, List, Optional

from . import domain
from .schema import normalize_event
from .store_events import EventStore
from .store_resources import ResourceStore
from .util import format_rfc3339, now_utc, sha256_hex

_UUID_KEYS = (
    "targetResourceUuid",
    "resourceUuid",
    "vmUuid",
    "vm_uuid",
    "instanceUuid",
    "hostUuid",
)


class EventIngest(object):
    def __init__(self, resources: ResourceStore, events: EventStore):
        self.resources = resources
        self.events = events

    # ----- public ---------------------------------------------------------
    def ingest(
        self,
        raw: Dict[str, Any],
        default_origin: str = "app",
        default_mode: str = "real",
        default_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        event, warnings = normalize_event(
            raw,
            default_origin=default_origin,
            default_mode=default_mode,
            default_source=default_source,
        )
        primary, extra_warnings = self._resolve_identity(event)
        warnings.extend(extra_warnings)
        if primary is not None:
            event["resource_id"] = primary["resource_id"]
            if primary.get("cluster_id"):
                event["cluster_id"] = primary["cluster_id"]
        dedup_key = raw.get("dedup_key") if isinstance(raw, dict) else None
        event_id, inserted = self.events.insert(event, dedup_key=dedup_key)
        event["event_id"] = event_id
        return {
            "event_id": event_id,
            "inserted": inserted,
            "event": event,
            "warnings": warnings,
        }

    def ingest_many(
        self,
        items: List[Dict[str, Any]],
        default_origin: str = "app",
        default_mode: str = "real",
        default_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        inserted = 0
        duplicates = 0
        event_ids: List[str] = []
        warnings: List[str] = []
        for raw in items:
            result = self.ingest(
                raw,
                default_origin=default_origin,
                default_mode=default_mode,
                default_source=default_source,
            )
            event_ids.append(result["event_id"])
            warnings.extend(result["warnings"])
            if result["inserted"]:
                inserted += 1
            else:
                duplicates += 1
        return {
            "inserted": inserted,
            "duplicates": duplicates,
            "event_ids": event_ids,
            "warnings": warnings,
        }

    # ----- identity -------------------------------------------------------
    def _canonical_container_id(self, value: str) -> str:
        """短容器 ID（12 位短 ID / 主机名）按前缀归一为完整 64 位 ID。

        AppEvent 生产者（agent-service）只能拿到容器的 12 位短 ID，而 cgroup/eBPF
        采集使用完整 ID；这里按前缀匹配已有容器资源，保证两类信号落到同一资源。
        """
        if len(value) >= 64:
            return value
        row = self.resources.find_container_by_prefix(value)
        if row and row.get("container_id"):
            return row["container_id"]
        return value

    def _resolve_identity(self, event: Dict[str, Any]):
        payload = event.get("payload") or {}
        warnings: List[str] = []

        container_row = None
        container_value = _nested(payload, ("container_id", "containerId"))
        if container_value:
            normalized = domain.normalize_container_id(container_value)
            if normalized:
                canonical = self._canonical_container_id(normalized)
                container_row = self._ensure_container(domain.container_id(canonical), event, canonical)

        service_row = None
        service_name = _nested(payload, ("service", "service_name", "serviceName"))
        if service_name:
            service_row = self._ensure_service(domain.service_id(service_name), event, str(service_name))

        task_row = self._ensure_task(event, service_row, container_row)
        if container_row and service_row:
            self._link(service_row["resource_id"], container_row["resource_id"], domain.REL_RUNS_ON, event)

        explicit = event.get("resource_id")
        if explicit:
            row = self._lazy_get(explicit, event)
            return row, warnings

        # 应用层优先：带容器/服务/任务归属的事件挂到最具体实体。
        # 例：AppEvent 同时带 container_id 与 vm_uuid 时，事件主体应为 container（而非 vm），
        # 否则任务证据会错误地上卷到 VM，影响 RCA 的资源邻接度与影响范围。
        if container_row:
            return container_row, warnings
        if service_row:
            return service_row, warnings
        if task_row:
            return task_row, warnings

        for key in _UUID_KEYS:
            value = _nested(payload, (key,))
            if not value:
                continue
            row = self.resources.get_by_uuid(str(value))
            if row:
                return row, warnings
            if key in ("vmUuid", "vm_uuid", "instanceUuid"):
                return self._lazy_get(domain.vm_id(str(value)), event), warnings
            if key == "hostUuid":
                return self._lazy_get(domain.host_id(str(value)), event), warnings

        return None, warnings

    def _ensure_task(self, event, service_row, container_row):
        task_id = event.get("task_id")
        if not task_id:
            return None
        rid = domain.task_id(task_id)
        row = self._lazy_get(rid, event, kind=domain.KIND_TASK, name=str(task_id))
        if service_row:
            self._link(rid, service_row["resource_id"], domain.REL_RUNS_ON, event)
        if container_row:
            self._link(rid, container_row["resource_id"], domain.REL_RUNS_ON, event)
        return row

    def _ensure_service(self, rid: str, event: Dict[str, Any], name: str):
        return self._lazy_get(rid, event, kind=domain.KIND_SERVICE, name=name)

    def _ensure_container(self, rid: str, event: Dict[str, Any], container_key: str):
        payload = event.get("payload") or {}
        # 容器真实名：container.discovered / cAdvisor 提供（attributes.name），缺省回退短 ID 占位
        display_name = _nested(payload, ("name", "container_name", "containerName"))
        # VM 归属：payload.attributes.vm_uuid（方案 §5.3）；用于建立 VM --contains--> Container 边
        vm_uuid = _nested(payload, ("vm_uuid", "vmUuid", "instanceUuid", "vm_instance_uuid"))
        vm_rid = domain.vm_id(str(vm_uuid)) if vm_uuid else None
        row = self._lazy_get(
            rid,
            event,
            kind=domain.KIND_CONTAINER,
            name=(str(display_name) if display_name else None),
            container_id=container_key,
            vm_id=vm_rid,
        )
        if vm_rid:
            self._link(vm_rid, rid, domain.REL_CONTAINS, event)
        return row

    def _lazy_get(
        self,
        resource_id: str,
        event: Dict[str, Any],
        kind: Optional[str] = None,
        name: Optional[str] = None,
        container_id: Optional[str] = None,
        vm_id: Optional[str] = None,
    ):
        row = self.resources.get(resource_id)
        payload = event.get("payload") or {}
        attributes = {
            "last_event_type": event.get("event_type"),
            "last_observed_at": event.get("observed_at"),
        }
        status = payload.get("status")
        if status:
            attributes["status"] = status
        # 名称优先级：显式真实名 > 已有名 > 容器 ID 短占位（仅对新建且无名的容器兜底）
        resolved_name = name or (row or {}).get("name")
        if not resolved_name and container_id:
            resolved_name = container_id[:12]
        record = {
            "resource_id": resource_id,
            "kind": (row or {}).get("kind") or kind or domain.kind_of(resource_id) or "unknown",
            "name": resolved_name,
            "container_id": (row or {}).get("container_id") or container_id,
            "vm_id": vm_id or (row or {}).get("vm_id"),
            "correlation_id": event.get("correlation_id") or (row or {}).get("correlation_id"),
            "origin": (row or {}).get("origin") or event.get("origin"),
            "mode": event.get("mode"),
            "labels": {},
            "attributes": attributes,
            "observed_at": event.get("observed_at"),
        }
        self.resources.upsert(record)
        return self.resources.get(resource_id)

    def _link(self, src_id: str, dst_id: str, relation: str, event: Dict[str, Any]) -> None:
        if not src_id or not dst_id or src_id == dst_id:
            return
        self.resources.upsert_edge(
            {
                "src_id": src_id,
                "dst_id": dst_id,
                "relation": relation,
                "origin": event.get("origin") or "app",
                "mode": event.get("mode") or "real",
                "labels": {},
                "observed_at": event.get("observed_at"),
            }
        )


def _nested(payload: Dict[str, Any], keys) -> Any:
    """Look up a key at payload top level, then inside ``payload.attributes``."""
    for key in keys:
        if payload.get(key):
            return payload[key]
    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        for key in keys:
            if attributes.get(key):
                return attributes[key]
    return None


def dedup_key_for(origin: str, source_event_id: str) -> str:
    return "%s:%s" % (origin, sha256_hex(source_event_id)[:32])


def touch_ingest_time() -> str:
    return format_rfc3339(now_utc())
