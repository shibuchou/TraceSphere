"""Resource Registry storage: resources + resource graph edges."""

from typing import Any, Dict, Iterable, List, Optional, Sequence

from .db import Database
from .util import format_rfc3339, json_dumps, json_loads, merge_dicts, now_utc


class ResourceStore(object):
    def __init__(self, db: Database):
        self.db = db

    # ----- writes ---------------------------------------------------------
    def upsert(self, record: Dict[str, Any]) -> str:
        resource_id = record.get("resource_id")
        if not resource_id:
            raise ValueError("resource record requires resource_id")
        now = format_rfc3339(now_utc())
        existing = self.db.query_one(
            "SELECT resource_id, name, state, cluster_id, zone_id, host_id, vm_id, container_id, "
            "correlation_id, labels, attributes, origin, mode FROM resources WHERE resource_id = ?",
            (resource_id,),
        )
        if existing:
            labels = merge_dicts(json_loads(existing.get("labels"), {}), record.get("labels"))
            attributes = merge_dicts(json_loads(existing.get("attributes"), {}), record.get("attributes"))
            self.db.execute(
                "UPDATE resources SET name = COALESCE(?, name), state = COALESCE(?, state), "
                "cluster_id = COALESCE(?, cluster_id), zone_id = COALESCE(?, zone_id), "
                "host_id = COALESCE(?, host_id), vm_id = COALESCE(?, vm_id), "
                "container_id = COALESCE(?, container_id), correlation_id = COALESCE(?, correlation_id), "
                "origin = COALESCE(?, origin), mode = COALESCE(?, mode), "
                "labels = ?, attributes = ?, observed_at = COALESCE(?, observed_at), updated_at = ? "
                "WHERE resource_id = ?",
                (
                    record.get("name"),
                    record.get("state"),
                    record.get("cluster_id"),
                    record.get("zone_id"),
                    record.get("host_id"),
                    record.get("vm_id"),
                    record.get("container_id"),
                    record.get("correlation_id"),
                    record.get("origin"),
                    record.get("mode"),
                    json_dumps(labels),
                    json_dumps(attributes),
                    record.get("observed_at"),
                    now,
                    resource_id,
                ),
            )
            return resource_id
        self.db.execute(
            "INSERT INTO resources (resource_id, kind, name, state, cluster_id, zone_id, host_id, vm_id, "
            "container_id, correlation_id, origin, mode, labels, attributes, observed_at, ingested_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                resource_id,
                record.get("kind") or "unknown",
                record.get("name"),
                record.get("state"),
                record.get("cluster_id"),
                record.get("zone_id"),
                record.get("host_id"),
                record.get("vm_id"),
                record.get("container_id"),
                record.get("correlation_id"),
                record.get("origin") or "unknown",
                record.get("mode") or "real",
                json_dumps(record.get("labels") or {}),
                json_dumps(record.get("attributes") or {}),
                record.get("observed_at"),
                now,
                now,
            ),
        )
        return resource_id

    def upsert_many(self, records: Iterable[Dict[str, Any]]) -> int:
        count = 0
        with self.db.tx():
            for record in records:
                self.upsert(record)
                count += 1
        return count

    def upsert_edge(self, edge: Dict[str, Any]) -> None:
        if not edge.get("src_id") or not edge.get("dst_id"):
            raise ValueError("edge requires src_id and dst_id")
        now = format_rfc3339(now_utc())
        self.db.execute(
            "INSERT INTO resource_edges (src_id, dst_id, relation, origin, mode, labels, observed_at, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(src_id, dst_id, relation) DO UPDATE SET "
            "origin = excluded.origin, mode = excluded.mode, labels = excluded.labels, "
            "observed_at = COALESCE(excluded.observed_at, resource_edges.observed_at), ingested_at = excluded.ingested_at",
            (
                edge.get("src_id"),
                edge.get("dst_id"),
                edge.get("relation") or "related_to",
                edge.get("origin") or "unknown",
                edge.get("mode") or "real",
                json_dumps(edge.get("labels") or {}),
                edge.get("observed_at"),
                now,
            ),
        )

    def upsert_edges(self, edges: Iterable[Dict[str, Any]]) -> int:
        count = 0
        with self.db.tx():
            for edge in edges:
                self.upsert_edge(edge)
                count += 1
        return count

    # ----- reads ----------------------------------------------------------
    def get(self, resource_id: str) -> Optional[Dict[str, Any]]:
        return self._decorate(
            self.db.query_one("SELECT * FROM resources WHERE resource_id = ?", (resource_id,))
        )

    def get_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        if not uuid:
            return None
        row = self.db.query_one(
            "SELECT * FROM resources WHERE resource_id = ? "
            "OR substr(resource_id, instr(resource_id, ':') + 1) = ? LIMIT 1",
            (uuid, uuid),
        )
        return self._decorate(row)

    def find_by_name(self, kind: str, name: str) -> Optional[Dict[str, Any]]:
        row = self.db.query_one(
            "SELECT * FROM resources WHERE kind = ? AND name = ? LIMIT 1",
            (kind, name),
        )
        return self._decorate(row)

    def find_container_by_prefix(self, prefix: str) -> Optional[Dict[str, Any]]:
        """按容器 ID 前缀（12 位短 ID）查找容器资源，用于统一短/长 ID。"""
        if not prefix:
            return None
        row = self.db.query_one(
            "SELECT * FROM resources WHERE kind = 'container' AND container_id LIKE ? "
            "ORDER BY length(container_id) DESC LIMIT 1",
            (prefix + "%",),
        )
        return self._decorate(row)

    def list(
        self,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        cluster_id: Optional[str] = None,
        vm_id: Optional[str] = None,
        host_id: Optional[str] = None,
        container_id: Optional[str] = None,
        state: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        where, params = _build_resource_filters(
            kind, name, cluster_id, vm_id, host_id, container_id, state, q
        )
        params.extend([max(1, min(int(limit or 200), 2000)), max(0, int(offset or 0))])
        rows = self.db.query(
            "SELECT * FROM resources%s ORDER BY kind, name, resource_id LIMIT ? OFFSET ?" % where,
            params,
        )
        return [self._decorate(row) for row in rows]

    def count(
        self,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        cluster_id: Optional[str] = None,
        vm_id: Optional[str] = None,
        host_id: Optional[str] = None,
        container_id: Optional[str] = None,
        state: Optional[str] = None,
        q: Optional[str] = None,
    ) -> int:
        where, params = _build_resource_filters(
            kind, name, cluster_id, vm_id, host_id, container_id, state, q
        )
        return int(self.db.scalar("SELECT COUNT(*) FROM resources%s" % where, params) or 0)

    def find_container_by_prefix(self, prefix: str) -> Optional[Dict[str, Any]]:
        if not prefix:
            return None
        row = self.db.query_one(
            "SELECT * FROM resources WHERE kind = 'container' AND container_id LIKE ? LIMIT 1",
            ("%s%%" % prefix,),
        )
        return self._decorate(row)

    def edges(self, resource_id: str, direction: str = "both", relation: Optional[str] = None) -> List[Dict[str, Any]]:
        direction = (direction or "both").lower()
        clauses = []
        params: List[Any] = []
        if direction in ("out", "both"):
            clauses.append("src_id = ?")
            params.append(resource_id)
        if direction in ("in", "both"):
            clauses.append("dst_id = ?")
            params.append(resource_id)
        where = "(%s)" % " OR ".join(clauses) if clauses else "1=0"
        if relation:
            where += " AND relation = ?"
            params.append(relation)
        rows = self.db.query(
            "SELECT * FROM resource_edges WHERE %s ORDER BY relation, src_id, dst_id" % where,
            params,
        )
        result = []
        for row in rows:
            row = dict(row)
            row["labels"] = json_loads(row.get("labels"), {})
            row["direction"] = "out" if row["src_id"] == resource_id else "in"
            row["neighbor_id"] = row["dst_id"] if row["direction"] == "out" else row["src_id"]
            result.append(row)
        return result

    def subgraph(self, resource_id: str, depth: int = 2, direction: str = "both") -> Dict[str, Any]:
        depth = max(1, min(int(depth or 2), 5))
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: Dict[str, Dict[str, Any]] = {}

        def ensure_node(node_id: str) -> None:
            if node_id in nodes:
                return
            resource = self.get(node_id)
            if resource:
                nodes[node_id] = resource
            else:
                kind = node_id.split(":", 1)[0] if ":" in node_id else "unknown"
                nodes[node_id] = {
                    "resource_id": node_id,
                    "kind": kind,
                    "name": None,
                    "state": None,
                    "labels": {},
                    "attributes": {},
                    "missing": True,
                }

        ensure_node(resource_id)
        frontier = [resource_id]
        for _ in range(depth):
            next_frontier: List[str] = []
            for node_id in frontier:
                for edge in self.edges(node_id, direction=direction):
                    key = "%s|%s|%s" % (edge["src_id"], edge["dst_id"], edge["relation"])
                    edges[key] = {
                        "src_id": edge["src_id"],
                        "dst_id": edge["dst_id"],
                        "relation": edge["relation"],
                        "origin": edge.get("origin"),
                        "mode": edge.get("mode"),
                        "labels": edge.get("labels") or {},
                    }
                    neighbor = edge["neighbor_id"]
                    if neighbor not in nodes:
                        ensure_node(neighbor)
                        next_frontier.append(neighbor)
            frontier = next_frontier
            if not frontier:
                break
        return {
            "root": resource_id,
            "depth": depth,
            "direction": direction,
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
        }

    def set_fields(self, resource_id: str, **fields: Any) -> None:
        allowed = {
            "name",
            "state",
            "cluster_id",
            "zone_id",
            "host_id",
            "vm_id",
            "container_id",
            "correlation_id",
            "labels",
            "attributes",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        if "labels" in updates:
            updates["labels"] = json_dumps(updates["labels"])
        if "attributes" in updates:
            updates["attributes"] = json_dumps(updates["attributes"])
        assignments = ", ".join("%s = ?" % key for key in updates)
        params: Sequence[Any] = list(updates.values()) + [format_rfc3339(now_utc()), resource_id]
        self.db.execute(
            "UPDATE resources SET %s, updated_at = ? WHERE resource_id = ?" % assignments,
            params,
        )

    @staticmethod
    def _decorate(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        row = dict(row)
        row["labels"] = json_loads(row.get("labels"), {})
        row["attributes"] = json_loads(row.get("attributes"), {})
        return row


def _build_resource_filters(
    kind: Optional[str],
    name: Optional[str],
    cluster_id: Optional[str],
    vm_id: Optional[str],
    host_id: Optional[str],
    container_id: Optional[str],
    state: Optional[str],
    q: Optional[str],
):
    clauses: List[str] = []
    params: List[Any] = []
    for column, value in (
        ("kind", kind),
        ("name", name),
        ("cluster_id", cluster_id),
        ("vm_id", vm_id),
        ("host_id", host_id),
        ("container_id", container_id),
        ("state", state),
    ):
        if value:
            clauses.append("%s = ?" % column)
            params.append(value)
    if q:
        clauses.append("(name LIKE ? OR resource_id LIKE ?)")
        pattern = "%%%s%%" % q
        params.extend([pattern, pattern])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
