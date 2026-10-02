"""Map raw ZSvirt / ZStack API inventories into the TraceSphere domain model.

The same mapper is used by :class:`~tsplatform.zsvirt.rest.RESTProvider` and
:class:`~tsplatform.zsvirt.fixture.FixtureProvider`, guaranteeing both
providers produce one domain model (方案 §4.2).

Mappers are intentionally defensive: unknown fields are kept inside
``attributes.raw`` so field drifts are visible without breaking ingestion.
"""

from typing import Any, Dict, List, Optional

from .. import domain
from ..util import format_rfc3339, now_utc, parse_timestamp, safe_severity
from .base import EdgeRecord, ResourceRecord, Snapshot

COLLECTIONS = (
    "zones",
    "clusters",
    "hosts",
    "vms",
    "images",
    "l3_networks",
    "l2_networks",
    "port_groups",
    "primary_storages",
    "backup_storages",
    "instance_offerings",
)


def inventories(response: Any) -> List[Dict[str, Any]]:
    """Extract ``inventories`` from a ZStack response (or a single inventory)."""
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        items = response.get("inventories")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        # ZWatch events use {"success": true, "events": [...]}
        items = response.get("events")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        single = response.get("inventory")
        if isinstance(single, dict):
            return [single]
    return []


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


class _Mapper(object):
    def __init__(self, mode: str, provider: str, captured_at: Optional[str] = None):
        self.mode = mode
        self.provider = provider
        self.captured_at = captured_at or format_rfc3339(now_utc())
        self.resources: List[ResourceRecord] = []
        self.edges: List[EdgeRecord] = []

    def resource(
        self,
        resource_id: str,
        kind: str,
        name: Optional[str] = None,
        state: Optional[str] = None,
        cluster_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        host_id: Optional[str] = None,
        vm_id: Optional[str] = None,
        container_id: Optional[str] = None,
        labels: Optional[Dict[str, Any]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        observed_at: Optional[str] = None,
    ) -> None:
        self.resources.append(
            ResourceRecord(
                resource_id=resource_id,
                kind=kind,
                name=name,
                state=state,
                cluster_id=cluster_id,
                zone_id=zone_id,
                host_id=host_id,
                vm_id=vm_id,
                container_id=container_id,
                origin="zsvirt",
                mode=self.mode,
                labels=labels or {},
                attributes=attributes or {},
                observed_at=observed_at or self.captured_at,
            )
        )

    def edge(self, src_id: Optional[str], dst_id: Optional[str], relation: str, labels: Optional[Dict[str, Any]] = None) -> None:
        if not src_id or not dst_id or src_id == dst_id:
            return
        self.edges.append(
            EdgeRecord(
                src_id=src_id,
                dst_id=dst_id,
                relation=relation,
                origin="zsvirt",
                mode=self.mode,
                labels=labels or {},
                observed_at=self.captured_at,
            )
        )

    # ----- collections ---------------------------------------------------
    def map_zones(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            self.resource(
                domain.zone_id(uuid),
                domain.KIND_ZONE,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")),
                labels={"zsvirt.type": _text(inv.get("type")) or "Zone"},
                attributes={"raw": _json_safe(inv)},
            )

    def map_clusters(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            zone_uuid = _text(inv.get("zoneUuid"))
            self.resource(
                domain.cluster_id(uuid),
                domain.KIND_CLUSTER,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")),
                zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
                labels={"zsvirt.type": _text(inv.get("type")) or "Cluster"},
                attributes={
                    "hypervisorType": _text(inv.get("hypervisorType")),
                    "raw": _json_safe(inv),
                },
            )
            self.edge(domain.zone_id(zone_uuid) if zone_uuid else None, domain.cluster_id(uuid), domain.REL_CONTAINS)

    def map_hosts(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            cluster_uuid = _text(inv.get("clusterUuid"))
            zone_uuid = _text(inv.get("zoneUuid"))
            self.resource(
                domain.host_id(uuid),
                domain.KIND_HOST,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")) or _text(inv.get("status")),
                cluster_id=domain.cluster_id(cluster_uuid) if cluster_uuid else None,
                zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
                labels={
                    "zsvirt.hypervisor": _text(inv.get("hypervisorType")) or "KVM",
                    "zsvirt.status": _text(inv.get("status")),
                },
                attributes={
                    "managementIp": _text(inv.get("managementIp")),
                    "cpuNum": inv.get("cpuNum"),
                    "cpuSpeed": inv.get("cpuSpeed"),
                    "totalCpuCapacity": inv.get("totalCpuCapacity"),
                    "availableCpuCapacity": inv.get("availableCpuCapacity"),
                    "totalMemoryCapacity": inv.get("totalMemoryCapacity"),
                    "availableMemoryCapacity": inv.get("availableMemoryCapacity"),
                    "osDistribution": _text(inv.get("osDistribution")),
                    "raw": _json_safe(inv),
                },
            )
            self.edge(domain.cluster_id(cluster_uuid) if cluster_uuid else None, domain.host_id(uuid), domain.REL_CONTAINS)

    def map_vms(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            vm_rid = domain.vm_id(uuid)
            host_uuid = _text(inv.get("hostUuid")) or _text(inv.get("lastHostUuid"))
            cluster_uuid = _text(inv.get("clusterUuid"))
            zone_uuid = _text(inv.get("zoneUuid"))
            nics = [nic for nic in (inv.get("vmNics") or []) if isinstance(nic, dict)]
            ips: List[str] = []
            for nic in nics:
                candidates = [_text(nic.get("ip"))]
                used = nic.get("usedIps")
                if isinstance(used, list):
                    candidates.extend(_text(ip) for ip in used)
                for ip in candidates:
                    if ip and ip not in ips:
                        ips.append(ip)
            macs = [mac for mac in (_text(nic.get("mac")) for nic in nics) if mac]
            volumes = [vol for vol in (inv.get("allVolumes") or []) if isinstance(vol, dict)]
            image_uuid = _text(inv.get("imageUuid"))
            self.resource(
                vm_rid,
                domain.KIND_VM,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")),
                cluster_id=domain.cluster_id(cluster_uuid) if cluster_uuid else None,
                zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
                host_id=domain.host_id(host_uuid) if host_uuid else None,
                labels={
                    "zsvirt.type": _text(inv.get("type")) or "UserVm",
                    "zsvirt.platform": _text(inv.get("platform")),
                },
                attributes={
                    "cpuNum": inv.get("cpuNum"),
                    "cpuSpeed": inv.get("cpuSpeed"),
                    "memorySize": inv.get("memorySize"),
                    "imageUuid": image_uuid,
                    "instanceOfferingUuid": _text(inv.get("instanceOfferingUuid")),
                    "rootVolumeUuid": _text(inv.get("rootVolumeUuid")),
                    "defaultL3NetworkUuid": _text(inv.get("defaultL3NetworkUuid")),
                    "ips": ips,
                    "macs": macs,
                    "nics": _json_safe(nics),
                    "volumes": _json_safe(volumes),
                    "createDate": _text(inv.get("createDate")),
                    "lastOpDate": _text(inv.get("lastOpDate")),
                    "raw": _json_safe(inv),
                },
            )
            if host_uuid:
                self.edge(domain.host_id(host_uuid), vm_rid, domain.REL_CONTAINS)
            if image_uuid:
                self.edge(vm_rid, domain.image_id(image_uuid), domain.REL_USES)
            attached_networks = set()
            for nic in nics:
                l3_uuid = _text(nic.get("l3NetworkUuid"))
                if l3_uuid:
                    attached_networks.add(l3_uuid)
                    self.edge(
                        vm_rid,
                        domain.network_id(l3_uuid),
                        domain.REL_ATTACHED_TO,
                        labels={
                            "ip": _text(nic.get("ip")),
                            "mac": _text(nic.get("mac")),
                            "deviceId": nic.get("deviceId"),
                        },
                    )
            default_l3 = _text(inv.get("defaultL3NetworkUuid"))
            if default_l3:
                attached_networks.add(default_l3)
            for l3_uuid in attached_networks:
                self.edge(
                    vm_rid,
                    domain.network_id(l3_uuid),
                    domain.REL_ATTACHED_TO,
                    labels={"default": str(l3_uuid == default_l3).lower()},
                )
            for vol in volumes:
                vol_uuid = _text(vol.get("uuid"))
                if not vol_uuid:
                    continue
                vol_rid = domain.volume_id(vol_uuid)
                ps_uuid = _text(vol.get("primaryStorageUuid"))
                self.resource(
                    vol_rid,
                    domain.KIND_VOLUME,
                    name=_text(vol.get("name"))
                    or "%s-%s" % (_text(inv.get("name")) or uuid[:8], _text(vol.get("type")) or "Volume"),
                    state=_text(vol.get("state")),
                    vm_id=vm_rid,
                    cluster_id=domain.cluster_id(cluster_uuid) if cluster_uuid else None,
                    zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
                    labels={"zsvirt.type": _text(vol.get("type")) or "Volume"},
                    attributes={
                        "size": vol.get("size"),
                        "deviceId": vol.get("deviceId"),
                        "primaryStorageUuid": ps_uuid,
                        "installPath": _text(vol.get("installPath")),
                        "raw": _json_safe(vol),
                    },
                )
                self.edge(vm_rid, vol_rid, domain.REL_HAS_VOLUME)
                if ps_uuid:
                    self.edge(vol_rid, domain.datastore_id(ps_uuid), domain.REL_ASSIGNED_TO)

    def map_images(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            self.resource(
                domain.image_id(uuid),
                domain.KIND_IMAGE,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")) or _text(inv.get("status")),
                labels={
                    "zsvirt.platform": _text(inv.get("platform")),
                    "zsvirt.format": _text(inv.get("format")),
                },
                attributes={
                    "format": _text(inv.get("format")),
                    "platform": _text(inv.get("platform")),
                    "architecture": _text(inv.get("architecture")),
                    "size": inv.get("size"),
                    "actualSize": inv.get("actualSize"),
                    "mediaType": _text(inv.get("mediaType")),
                    "status": _text(inv.get("status")),
                    "system": inv.get("system"),
                    "raw": _json_safe(inv),
                },
            )

    def _map_network(self, inv: Dict[str, Any], api_collection: str) -> None:
        uuid = _text(inv.get("uuid"))
        if not uuid:
            return
        zone_uuid = _text(inv.get("zoneUuid"))
        l2_uuid = _text(inv.get("l2NetworkUuid"))
        ip_ranges = [ipr for ipr in (inv.get("ipRanges") or []) if isinstance(ipr, dict)]
        self.resource(
            domain.network_id(uuid),
            domain.KIND_NETWORK,
            name=_text(inv.get("name")),
            state=_text(inv.get("state")),
            zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
            labels={
                "zsvirt.type": _text(inv.get("type")) or api_collection,
                "zsvirt.api": api_collection,
                "zsvirt.category": _text(inv.get("category")),
            },
            attributes={
                "apiCollection": api_collection,
                "apiType": _text(inv.get("type")),
                "l2NetworkUuid": l2_uuid,
                "vSwitchUuid": _text(inv.get("vSwitchUuid")),
                "category": _text(inv.get("category")),
                "dns": _json_safe(inv.get("dns")),
                "ipRanges": _json_safe(ip_ranges),
                "networkCidr": _text(inv.get("networkCidr")),
                "ipVersion": inv.get("ipVersion"),
                "enableIPAM": inv.get("enableIPAM"),
                "physicalInterface": _text(inv.get("physicalInterface")),
                "vSwitchType": _text(inv.get("vSwitchType")),
                "vlanId": inv.get("vlanId"),
                "vlanMode": _text(inv.get("vlanMode")),
                "networkServices": _json_safe(inv.get("networkServices")),
                "raw": _json_safe(inv),
            },
        )
        if l2_uuid:
            self.edge(domain.network_id(uuid), domain.network_id(l2_uuid), domain.REL_OVER)
        vswitch_uuid = _text(inv.get("vSwitchUuid"))
        if vswitch_uuid:
            self.edge(domain.network_id(uuid), domain.network_id(vswitch_uuid), domain.REL_OVER)

    def map_l3_networks(self, response: Any) -> None:
        for inv in inventories(response):
            self._map_network(inv, "l3-networks")

    def map_l2_networks(self, response: Any) -> None:
        for inv in inventories(response):
            self._map_network(inv, "l2-networks")

    def map_port_groups(self, response: Any) -> None:
        for inv in inventories(response):
            self._map_network(inv, "port-groups")

    def map_primary_storages(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            zone_uuid = _text(inv.get("zoneUuid"))
            self.resource(
                domain.datastore_id(uuid),
                domain.KIND_DATASTORE,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")) or _text(inv.get("status")),
                zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
                labels={"zsvirt.type": _text(inv.get("type")) or "PrimaryStorage"},
                attributes={
                    "totalCapacity": inv.get("totalCapacity"),
                    "availableCapacity": inv.get("availableCapacity"),
                    "raw": _json_safe(inv),
                },
            )
            self.edge(domain.zone_id(zone_uuid) if zone_uuid else None, domain.datastore_id(uuid), domain.REL_CONTAINS)

    def map_backup_storages(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            zone_uuid = _text(inv.get("zoneUuid"))
            self.resource(
                domain.datastore_id(uuid),
                domain.KIND_DATASTORE,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")) or _text(inv.get("status")),
                zone_id=domain.zone_id(zone_uuid) if zone_uuid else None,
                labels={"zsvirt.type": _text(inv.get("type")) or "BackupStorage"},
                attributes={
                    "totalCapacity": inv.get("totalCapacity"),
                    "availableCapacity": inv.get("availableCapacity"),
                    "raw": _json_safe(inv),
                },
            )
            self.edge(domain.zone_id(zone_uuid) if zone_uuid else None, domain.datastore_id(uuid), domain.REL_CONTAINS)

    def map_instance_offerings(self, response: Any) -> None:
        for inv in inventories(response):
            uuid = _text(inv.get("uuid"))
            if not uuid:
                continue
            self.resource(
                domain.offering_id(uuid),
                domain.KIND_OFFERING,
                name=_text(inv.get("name")),
                state=_text(inv.get("state")),
                labels={"zsvirt.type": "InstanceOffering"},
                attributes={
                    "cpuNum": inv.get("cpuNum"),
                    "cpuSpeed": inv.get("cpuSpeed"),
                    "memorySize": inv.get("memorySize"),
                    "type": _text(inv.get("type")),
                    "raw": _json_safe(inv),
                },
            )


def snapshot_from_raw(
    raw: Dict[str, Any],
    mode: str = "mock",
    provider: str = "fixture",
    captured_at: Optional[str] = None,
) -> Snapshot:
    """Convert raw ZStack responses keyed by collection name into a Snapshot."""
    mapper = _Mapper(mode=mode, provider=provider, captured_at=captured_at)
    mapper.map_zones(raw.get("zones"))
    mapper.map_clusters(raw.get("clusters"))
    mapper.map_hosts(raw.get("hosts"))
    mapper.map_vms(raw.get("vms"))
    mapper.map_images(raw.get("images"))
    mapper.map_l3_networks(raw.get("l3_networks"))
    mapper.map_l2_networks(raw.get("l2_networks"))
    mapper.map_port_groups(raw.get("port_groups"))
    mapper.map_primary_storages(raw.get("primary_storages"))
    mapper.map_backup_storages(raw.get("backup_storages"))
    mapper.map_instance_offerings(raw.get("instance_offerings"))

    snapshot = Snapshot(
        resources=mapper.resources,
        edges=mapper.edges,
        alarms=inventories(raw.get("alarms")),
        events=inventories(raw.get("events")),
        provider=provider,
        mode=mode,
        captured_at=mapper.captured_at,
    )
    snapshot.counts = {
        "resources": len(snapshot.resources),
        "edges": len(snapshot.edges),
        "alarms": len(snapshot.alarms),
        "events": len(snapshot.events),
    }
    return snapshot


def _target_resource_uuid(inv: Dict[str, Any]) -> Optional[str]:
    """Resolve an alarm's target resource uuid from direct fields, labels, or actions."""
    for key in ("targetResourceUuid", "resourceUuid", "resourceId"):
        value = _text(inv.get(key))
        if value:
            return value
    labels = inv.get("labels")
    if isinstance(labels, dict):
        for key, value in labels.items():
            if str(key).lower().endswith("uuid") and value:
                return str(value)
    elif isinstance(labels, list):
        for item in labels:
            if not isinstance(item, dict):
                continue
            key = _text(item.get("key")) or ""
            value = item.get("value")
            if key.lower().endswith("uuid") and value:
                return str(value)
    return None


def alarm_inventories_to_events(
    alarm_inventories: List[Dict[str, Any]],
    mode: str,
    fallback_time: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """Convert ZStack AlarmVO inventories into Schema v1 alert events.

    ``/zwatch/alarms`` returns alarm *definitions* whose ``status`` is either
    ``Alarm`` (currently firing) or ``OK``. Only firing alarms become events by
    default, keeping the event stream free of 18 idle definitions (noise
    reduction, 方案 §6.2). Transitions are preserved through the dedup key
    (status + lastOpDate), so a new alarm activation is a new event.
    """
    events = []
    for inv in alarm_inventories:
        if not isinstance(inv, dict):
            continue
        status = _text(inv.get("status")) or _text(inv.get("alarmStatus"))
        if active_only and (status or "").lower() != "alarm":
            continue
        uuid = _text(inv.get("uuid")) or _text(inv.get("alarmUuid"))
        observed = parse_timestamp(
            inv.get("lastOpDate") or inv.get("createDate") or inv.get("alarmTime")
        )
        observed_at = format_rfc3339(observed) if observed else (fallback_time or format_rfc3339())
        severity = safe_severity(
            inv.get("emergencyLevel") or inv.get("severity") or inv.get("level")
        )
        target_uuid = _target_resource_uuid(inv)
        dedup = "zsvirt:alarm:%s:%s:%s" % (
            uuid or "unknown",
            (status or "").lower(),
            _text(inv.get("lastOpDate")) or observed_at,
        )
        events.append(
            {
                "schema_version": "v1",
                "origin": "zsvirt",
                "mode": mode,
                "observed_at": observed_at,
                "type": "alert",
                "event_type": "zsvirt.alarm",
                "resource_id": None,
                "severity": severity or "warning",
                "source": "zsvirt",
                "payload": {
                    "uuid": uuid,
                    "name": _text(inv.get("name")),
                    "status": status,
                    "metricName": _text(inv.get("metricName")),
                    "namespace": _text(inv.get("namespace")),
                    "targetResourceUuid": target_uuid,
                    "threshold": inv.get("threshold"),
                    "comparisonOperator": _text(inv.get("comparisonOperator")),
                    "period": inv.get("period"),
                    "repeatInterval": inv.get("repeatInterval"),
                    "emergencyLevel": _text(inv.get("emergencyLevel")),
                    "raw": _json_safe(inv),
                },
                "dedup_key": dedup,
            }
        )
    return events


def zsvirt_event_inventories_to_events(
    event_inventories: List[Dict[str, Any]],
    mode: str,
    fallback_time: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convert ZWatch events (``/zwatch/events``) into Schema v1 events.

    Real response shape: ``{"success": true, "events": [{namespace, name, labels,
    emergencyLevel, resourceId, time(epoch ms), dataUuid, ...}]}``.
    """
    events = []
    for inv in event_inventories:
        if not isinstance(inv, dict):
            continue
        uuid = _text(inv.get("dataUuid")) or _text(inv.get("uuid"))
        observed = parse_timestamp(
            inv.get("time") or inv.get("createDate") or inv.get("lastOpDate")
        )
        observed_at = format_rfc3339(observed) if observed else (fallback_time or format_rfc3339())
        name = _text(inv.get("name")) or "zsvirt.event"
        error_code = _text(inv.get("errorCode"))
        severity = safe_severity(inv.get("emergencyLevel")) or ("major" if error_code else "info")
        events.append(
            {
                "schema_version": "v1",
                "origin": "zsvirt",
                "mode": mode,
                "observed_at": observed_at,
                "type": "event",
                "event_type": "zsvirt.event",
                "resource_id": None,
                "severity": severity,
                "source": "zsvirt",
                "payload": {
                    "uuid": uuid,
                    "name": name,
                    "namespace": _text(inv.get("namespace")),
                    "resourceId": _text(inv.get("resourceId")),
                    "labels": _json_safe(inv.get("labels")),
                    "emergencyLevel": _text(inv.get("emergencyLevel")),
                    "readStatus": _text(inv.get("readStatus")),
                    "errorCode": error_code,
                    "raw": _json_safe(inv),
                },
                "dedup_key": "zsvirt:event:%s" % uuid if uuid else None,
            }
        )
    return events
