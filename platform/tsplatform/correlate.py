"""Correlation Engine (W1 minimal, extended in W2).

Groups events into clusters using:

- application anchor: ``correlation_id``
- system anchor: same ``resource_id`` within a time window
- topology: neighbors of the focus resources in the Resource Graph

The engine emits Evidence records with a machine-matchable ``signal``
(usually the event type) and a human-readable description. RCA (member C)
consumes these evidence items; B deliberately does not decide root causes.
"""

from typing import Any, Dict, List, Optional, Sequence, Set

from .schema import evidence_kind_for_origin
from .store_events import EventStore
from .store_evidence import ClusterStore, EvidenceStore
from .store_resources import ResourceStore
from .util import format_rfc3339, parse_timestamp, sha256_hex, truncate

MAX_FOCUS_RESOURCES = 5
MAX_NEIGHBORS = 50

RULE_CORRELATION_ID = "correlation.correlation_id"
RULE_RESOURCE_WINDOW = "correlation.same_resource_time_window"


class CorrelationEngine(object):
    def __init__(
        self,
        events: EventStore,
        resources: ResourceStore,
        evidence: EvidenceStore,
        clusters: ClusterStore,
        window_seconds: float = 5.0,
        max_events: int = 5000,
    ):
        self.events = events
        self.resources = resources
        self.evidence = evidence
        self.clusters = clusters
        self.window_seconds = float(window_seconds or 5.0)
        self.max_events = int(max_events or 5000)

    # ----- public ---------------------------------------------------------
    def correlate(
        self,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        resource_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        window_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        window = float(window_seconds or self.window_seconds)
        events = self.events.query(
            from_ts=from_ts,
            to_ts=to_ts,
            resource_id=resource_id,
            correlation_id=correlation_id,
            order="asc",
            limit=self.max_events,
        )

        groups: List[Dict[str, Any]] = []
        consumed: Set[str] = set()

        # pass 1: application anchor (correlation_id)
        by_correlation: Dict[str, List[Dict[str, Any]]] = {}
        for event in events:
            cid = event.get("correlation_id")
            if cid:
                by_correlation.setdefault(cid, []).append(event)
        for cid, group_events in by_correlation.items():
            group = self._build_group(cid, "correlation_id", group_events, window)
            # events attached through topology belong to this cluster; they must
            # not seed a duplicate resource-window cluster in pass 2
            consumed.update(event["event_id"] for event in group["events"])
            groups.append(group)

        # pass 2: resource anchor (system layer, no correlation_id)
        by_resource: Dict[str, List[Dict[str, Any]]] = {}
        for event in events:
            if event["event_id"] in consumed or event.get("correlation_id"):
                continue
            rid = event.get("resource_id")
            if rid:
                by_resource.setdefault(rid, []).append(event)
        for rid, group_events in by_resource.items():
            group = self._build_group(rid, "resource_id", group_events, window)
            consumed.update(event["event_id"] for event in group_events)
            groups.append(group)

        clusters_out = []
        total_evidence = 0
        for group in groups:
            cluster = self._persist_group(group)
            total_evidence += len(cluster.get("evidence", []))
            clusters_out.append(cluster)

        return {
            "window_seconds": window,
            "stats": {
                "events_considered": len(events),
                "clusters": len(clusters_out),
                "evidence": total_evidence,
            },
            "clusters": clusters_out,
        }

    # ----- grouping -------------------------------------------------------
    def _build_group(
        self,
        anchor: str,
        anchor_kind: str,
        seed_events: Sequence[Dict[str, Any]],
        window: float,
    ) -> Dict[str, Any]:
        all_events: Dict[str, Dict[str, Any]] = {event["event_id"]: event for event in seed_events}
        start = min(event["observed_at"] for event in seed_events)
        end = max(event["observed_at"] for event in seed_events)
        start_dt = parse_timestamp(start)
        end_dt = parse_timestamp(end)
        window_start = format_rfc3339(start_dt) if start_dt else start
        window_end = format_rfc3339(end_dt) if end_dt else end

        for related in self._topology_events(seed_events, window):
            if related["event_id"] not in all_events:
                all_events[related["event_id"]] = related
                if related["observed_at"] < window_start:
                    window_start = related["observed_at"]
                if related["observed_at"] > window_end:
                    window_end = related["observed_at"]

        ordered = sorted(all_events.values(), key=lambda item: (item["observed_at"], item["event_id"]))
        focus_resource = next((event.get("resource_id") for event in ordered if event.get("resource_id")), None)
        correlation_id = None
        if anchor_kind == "correlation_id":
            correlation_id = anchor
        else:
            correlation_id = next((event.get("correlation_id") for event in ordered if event.get("correlation_id")), None)
        rule = RULE_CORRELATION_ID if anchor_kind == "correlation_id" else RULE_RESOURCE_WINDOW
        event_ids = [event["event_id"] for event in ordered]
        cluster_key = sha256_hex("corr:" + "|".join(sorted(event_ids)))[:24]
        return {
            "cluster_key": cluster_key,
            "correlation_id": correlation_id,
            "resource_id": focus_resource,
            "rule": rule,
            "window_start": window_start,
            "window_end": window_end,
            "events": ordered,
            "summary": self._summary(ordered, focus_resource),
        }

    def _topology_events(self, seed_events: Sequence[Dict[str, Any]], window: float) -> List[Dict[str, Any]]:
        focus_ids: List[str] = []
        for event in seed_events:
            rid = event.get("resource_id")
            if rid and rid not in focus_ids:
                focus_ids.append(rid)
        if not focus_ids:
            return []
        start_dt = parse_timestamp(min(event["observed_at"] for event in seed_events))
        end_dt = parse_timestamp(max(event["observed_at"] for event in seed_events))
        if start_dt is None or end_dt is None:
            return []
        from_ts = format_rfc3339(start_dt - _delta(window))
        to_ts = format_rfc3339(end_dt + _delta(window))

        neighbor_ids: List[str] = []
        for rid in focus_ids[:MAX_FOCUS_RESOURCES]:
            neighbors = self._neighbor_ids(rid)
            for neighbor in neighbors:
                if neighbor not in neighbor_ids:
                    neighbor_ids.append(neighbor)
                if len(neighbor_ids) >= MAX_NEIGHBORS:
                    break
            if len(neighbor_ids) >= MAX_NEIGHBORS:
                break

        seen = {event["event_id"] for event in seed_events}
        related: List[Dict[str, Any]] = []
        for neighbor_id in neighbor_ids:
            for event in self.events.query(
                from_ts=from_ts,
                to_ts=to_ts,
                resource_id=neighbor_id,
                order="asc",
                limit=500,
            ):
                if event["event_id"] in seen:
                    continue
                seen.add(event["event_id"])
                related.append(event)
        return related

    def _neighbor_ids(self, resource_id: str) -> List[str]:
        ids = [resource_id]
        for edge in self.resources.edges(resource_id, direction="both"):
            neighbor = edge.get("neighbor_id")
            if neighbor and neighbor not in ids:
                ids.append(neighbor)
        return ids

    @staticmethod
    def _summary(events: Sequence[Dict[str, Any]], focus_resource: Optional[str]) -> str:
        signals = []
        for event in events:
            signal = event.get("event_type")
            if signal and signal not in signals:
                signals.append(signal)
        resources = {event.get("resource_id") for event in events if event.get("resource_id")}
        return "%d events, %d resources, signals=[%s] focus=%s" % (
            len(events),
            len(resources),
            ", ".join(signals[:6]),
            focus_resource or "-",
        )

    # ----- persistence ----------------------------------------------------
    def _persist_group(self, group: Dict[str, Any]) -> Dict[str, Any]:
        events = group["events"]
        event_ids = [event["event_id"] for event in events]
        cluster_id, created = self.clusters.upsert(
            {
                "cluster_key": group["cluster_key"],
                "correlation_id": group["correlation_id"],
                "resource_id": group["resource_id"],
                "rule": group["rule"],
                "window_start": group["window_start"],
                "window_end": group["window_end"],
                "status": "open",
                "event_ids": event_ids,
                "summary": group["summary"],
            }
        )
        evidence_items = [
            self._evidence_for(cluster_id, group["cluster_key"], event, group.get("correlation_id"))
            for event in events
        ]
        # add topology hints when multiple resources participate
        evidence_items.extend(self._adjacency_evidence(cluster_id, group["cluster_key"], events))
        receipt = self.evidence.insert_many(evidence_items)
        self.clusters.upsert(
            {
                "cluster_key": group["cluster_key"],
                "evidence_ids": receipt["evidence_ids"],
            }
        )
        self.events.set_cluster(event_ids, cluster_id)
        cluster = self.clusters.get(cluster_id) or {"cluster_id": cluster_id}
        cluster["created"] = created
        cluster["evidence"] = self.evidence.query(cluster_id=cluster_id, limit=200)
        return cluster

    def _evidence_for(
        self,
        cluster_id: str,
        cluster_key: str,
        event: Dict[str, Any],
        cluster_correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = event.get("payload") or {}
        description = "%s [%s]" % (event.get("event_type"), event.get("origin"))
        if event.get("resource_id"):
            resource = self.resources.get(event["resource_id"]) or {}
            description += " on %s" % (resource.get("name") or event["resource_id"])
        status = payload.get("status")
        if status:
            description += " status=%s" % status
        if event.get("severity"):
            description += " severity=%s" % event["severity"]
        payload_out = {
            "event_id": event["event_id"],
            "origin": event.get("origin"),
            "mode": event.get("mode"),
            "severity": event.get("severity"),
            "source": event.get("source"),
            "event_payload": _trim_payload(payload),
        }
        # 计数器/指标的数值提升到证据顶层：RCA 规则按 evidence.payload.value|delta 读取（API.md §1）
        for key in ("value", "delta", "unit", "threshold", "metric"):
            if payload.get(key) is not None:
                payload_out[key] = payload[key]
        if payload.get("value") is not None:
            description += " value=%s%s" % (payload.get("value"), payload.get("unit") or "")
        return {
            "cluster_id": cluster_id,
            "kind": evidence_kind_for_origin(event.get("origin")),
            "signal": event.get("event_type"),
            "description": description,
            "resource_id": event.get("resource_id"),
            "correlation_id": cluster_correlation_id or event.get("correlation_id"),
            "task_id": event.get("task_id"),
            "observed_at": event.get("observed_at"),
            "source_event_ids": [event["event_id"]],
            "payload": payload_out,
            "origin": event.get("origin"),
            "mode": event.get("mode"),
            "dedup_key": "corr:%s:%s" % (cluster_key, event["event_id"]),
        }

    def _adjacency_evidence(self, cluster_id: str, cluster_key: str, events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        resource_ids = []
        for event in events:
            rid = event.get("resource_id")
            if rid and rid not in resource_ids:
                resource_ids.append(rid)
        if len(resource_ids) < 2:
            return []
        anchors = {rid: event for rid, event in _resource_anchor(events).items()}
        items: List[Dict[str, Any]] = []
        for src in anchors:
            for edge in self.resources.edges(src, direction="out"):
                dst = edge.get("dst_id")
                if dst in resource_ids:
                    items.append(
                        {
                            "cluster_id": cluster_id,
                            "kind": "topology",
                            "signal": "topology.adjacency",
                            "description": "resource adjacency: %s -[%s]-> %s"
                            % (src, edge.get("relation"), dst),
                            "resource_id": src,
                            "correlation_id": None,
                            "task_id": None,
                            "observed_at": anchors[src]["observed_at"],
                            "source_event_ids": [anchors[src]["event_id"], anchors[dst]["event_id"]],
                            "payload": {
                                "src_id": src,
                                "dst_id": dst,
                                "relation": edge.get("relation"),
                            },
                            "origin": "platform",
                            "mode": events[0].get("mode"),
                            "dedup_key": "corr:%s:adj:%s:%s:%s"
                            % (cluster_key, src, edge.get("relation"), dst),
                        }
                    )
        return items


def _resource_anchor(events: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    anchors: Dict[str, Dict[str, Any]] = {}
    for event in events:
        rid = event.get("resource_id")
        if rid and rid not in anchors:
            anchors[rid] = event
    return anchors


def _trim_payload(payload: Dict[str, Any], limit: int = 2000) -> Dict[str, Any]:
    trimmed: Dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if isinstance(value, str):
            trimmed[key] = truncate(value, limit)
        else:
            trimmed[key] = value
    return trimmed


def _delta(seconds: float):
    import datetime

    return datetime.timedelta(seconds=seconds)
