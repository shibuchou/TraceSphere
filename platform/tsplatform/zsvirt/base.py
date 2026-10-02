"""ZSvirt provider interface and the shared domain model records."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResourceRecord:
    resource_id: str
    kind: str
    name: Optional[str] = None
    state: Optional[str] = None
    cluster_id: Optional[str] = None
    zone_id: Optional[str] = None
    host_id: Optional[str] = None
    vm_id: Optional[str] = None
    container_id: Optional[str] = None
    correlation_id: Optional[str] = None
    origin: str = "zsvirt"
    mode: str = "real"
    labels: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    observed_at: Optional[str] = None


@dataclass
class EdgeRecord:
    src_id: str
    dst_id: str
    relation: str
    origin: str = "zsvirt"
    mode: str = "real"
    labels: Dict[str, Any] = field(default_factory=dict)
    observed_at: Optional[str] = None


@dataclass
class Snapshot:
    """Normalized provider output: resources + edges (+ raw alarms/events)."""

    resources: List[ResourceRecord] = field(default_factory=list)
    edges: List[EdgeRecord] = field(default_factory=list)
    alarms: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    provider: str = "base"
    mode: str = "real"
    captured_at: Optional[str] = None
    counts: Dict[str, int] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)

    def counts_summary(self) -> Dict[str, int]:
        if self.counts:
            return dict(self.counts)
        return {
            "resources": len(self.resources),
            "edges": len(self.edges),
            "alarms": len(self.alarms),
            "events": len(self.events),
        }


class ZSvirtProvider(object):
    """Real/Fixture providers must produce the same :class:`Snapshot`."""

    name = "base"
    mode = "real"

    def snapshot(self) -> Snapshot:
        raise NotImplementedError

    @property
    def description(self) -> str:
        return "%s (%s)" % (self.name, self.mode)
