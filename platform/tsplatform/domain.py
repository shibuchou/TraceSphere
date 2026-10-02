"""Resource identity model (方案 §5.1/§5.3).

Canonical resource ids are ``<kind>:<key>`` so that ids from different
producers (zsvirt / cadvisor / eBPF / AppEvent) can be related without
collisions. Container ids keep the runtime id (full 64 hex when available);
lookups accept short-id prefixes.
"""

from typing import Optional, Tuple

KIND_HOST = "host"
KIND_VM = "vm"
KIND_CONTAINER = "container"
KIND_PROCESS = "process"
KIND_SERVICE = "service"
KIND_TASK = "task"
KIND_GPU = "gpu"
KIND_ZONE = "zone"
KIND_CLUSTER = "cluster"
KIND_NETWORK = "network"
KIND_IMAGE = "image"
KIND_DATASTORE = "datastore"
KIND_VOLUME = "volume"
KIND_OFFERING = "offering"

RESOURCE_KINDS = (
    KIND_HOST,
    KIND_VM,
    KIND_CONTAINER,
    KIND_PROCESS,
    KIND_SERVICE,
    KIND_TASK,
    KIND_GPU,
    KIND_ZONE,
    KIND_CLUSTER,
    KIND_NETWORK,
    KIND_IMAGE,
    KIND_DATASTORE,
    KIND_VOLUME,
    KIND_OFFERING,
)

_CONTAINER_PREFIXES = ("docker://", "containerd://", "cri-containerd://")

# Edge relation vocabulary (方案 §5.2)
REL_CONTAINS = "contains"
REL_ASSIGNED_TO = "assigned_to"
REL_ATTACHED_TO = "attached_to"
REL_USES = "uses"
REL_HAS_VOLUME = "has_volume"
REL_OVER = "over"
REL_PROVIDES = "provides"
REL_RUNS_ON = "runs_on"
REL_CALLS = "calls"
REL_SPAWNS = "spawns"


def make_id(kind: str, key: str) -> str:
    return "%s:%s" % (kind, key)


def parse_id(resource_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not resource_id or ":" not in resource_id:
        return None, resource_id
    kind, key = resource_id.split(":", 1)
    return kind, key


def kind_of(resource_id: Optional[str]) -> Optional[str]:
    return parse_id(resource_id)[0]


def key_of(resource_id: Optional[str]) -> Optional[str]:
    return parse_id(resource_id)[1]


def host_id(uuid: str) -> str:
    return make_id(KIND_HOST, uuid)


def vm_id(uuid: str) -> str:
    return make_id(KIND_VM, uuid)


def zone_id(uuid: str) -> str:
    return make_id(KIND_ZONE, uuid)


def cluster_id(uuid: str) -> str:
    return make_id(KIND_CLUSTER, uuid)


def network_id(uuid: str) -> str:
    return make_id(KIND_NETWORK, uuid)


def image_id(uuid: str) -> str:
    return make_id(KIND_IMAGE, uuid)


def datastore_id(uuid: str) -> str:
    return make_id(KIND_DATASTORE, uuid)


def volume_id(uuid: str) -> str:
    return make_id(KIND_VOLUME, uuid)


def offering_id(uuid: str) -> str:
    return make_id(KIND_OFFERING, uuid)


def normalize_container_id(value: Optional[str]) -> Optional[str]:
    """Strip runtime prefixes; keep the raw id (docker ids are lowercase hex)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    for prefix in _CONTAINER_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):]
            break
    return text or None


def container_id(value: str) -> Optional[str]:
    normalized = normalize_container_id(value)
    return make_id(KIND_CONTAINER, normalized) if normalized else None


def service_id(name: str) -> str:
    return make_id(KIND_SERVICE, str(name).strip())


def task_id(value: str) -> str:
    return make_id(KIND_TASK, str(value).strip())


def process_id(pid, start_time) -> str:
    return make_id(KIND_PROCESS, "%s:%s" % (pid, start_time))


def gpu_id(key: str) -> str:
    return make_id(KIND_GPU, str(key))
