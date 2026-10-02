"""Evidence + correlation cluster stores."""

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .db import Database
from .util import format_rfc3339, json_dumps, json_loads, new_id, now_utc


class EvidenceStore(object):
    def __init__(self, db: Database):
        self.db = db

    def insert(self, evidence: Dict[str, Any], dedup_key: Optional[str] = None) -> Tuple[str, bool]:
        evidence_id = evidence.get("evidence_id") or new_id("evd")
        key = dedup_key if dedup_key is not None else evidence.get("dedup_key")
        if key:
            existing = self.db.query_one("SELECT evidence_id FROM evidence WHERE dedup_key = ?", (key,))
            if existing:
                return existing["evidence_id"], False
        now = format_rfc3339(now_utc())
        self.db.execute(
            "INSERT INTO evidence (evidence_id, cluster_id, kind, signal, description, resource_id, "
            "correlation_id, task_id, observed_at, ingested_at, source_event_ids, payload, weight, origin, mode, "
            "created_at, dedup_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence_id,
                evidence.get("cluster_id"),
                evidence.get("kind") or "other",
                evidence.get("signal"),
                evidence.get("description"),
                evidence.get("resource_id"),
                evidence.get("correlation_id"),
                evidence.get("task_id"),
                evidence.get("observed_at") or now,
                evidence.get("ingested_at") or now,
                json_dumps(evidence.get("source_event_ids") or []),
                json_dumps(evidence.get("payload") or {}),
                evidence.get("weight"),
                evidence.get("origin"),
                evidence.get("mode"),
                now,
                key,
            ),
        )
        return evidence_id, True

    def insert_many(self, evidence_items: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        inserted = 0
        duplicates = 0
        evidence_ids: List[str] = []
        with self.db.tx():
            for item in evidence_items:
                evidence_id, is_new = self.insert(item)
                evidence_ids.append(evidence_id)
                if is_new:
                    inserted += 1
                else:
                    duplicates += 1
        return {"inserted": inserted, "duplicates": duplicates, "evidence_ids": evidence_ids}

    def get(self, evidence_id: str) -> Optional[Dict[str, Any]]:
        return self._decorate(
            self.db.query_one("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
        )

    def query(
        self,
        cluster_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        signal: Optional[str] = None,
        kind: Optional[str] = None,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
        order: str = "asc",
    ) -> List[Dict[str, Any]]:
        where, params = _build_evidence_where(
            cluster_id, correlation_id, resource_id, signal, kind, from_ts, to_ts
        )
        direction = "DESC" if str(order).lower() == "desc" else "ASC"
        params.extend([max(1, min(int(limit or 500), 5000)), max(0, int(offset or 0))])
        rows = self.db.query(
            "SELECT * FROM evidence%s ORDER BY observed_at %s, evidence_id %s LIMIT ? OFFSET ?"
            % (where, direction, direction),
            params,
        )
        return [self._decorate(row) for row in rows]

    def count(self, **filters: Any) -> int:
        where, params = _build_evidence_where(
            filters.get("cluster_id"),
            filters.get("correlation_id"),
            filters.get("resource_id"),
            filters.get("signal"),
            filters.get("kind"),
            filters.get("from_ts"),
            filters.get("to_ts"),
        )
        return int(self.db.scalar("SELECT COUNT(*) FROM evidence%s" % where, params) or 0)

    @staticmethod
    def _decorate(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        row = dict(row)
        row["payload"] = json_loads(row.get("payload"), {})
        row["source_event_ids"] = json_loads(row.get("source_event_ids"), [])
        return row


class ClusterStore(object):
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, cluster: Dict[str, Any]) -> Tuple[str, bool]:
        """Upsert by ``cluster_key``; merges event/evidence id lists."""
        key = cluster.get("cluster_key")
        now = format_rfc3339(now_utc())
        existing = None
        if key:
            existing = self.db.query_one("SELECT * FROM clusters WHERE cluster_key = ?", (key,))
        if existing:
            event_ids = _union(json_loads(existing.get("event_ids"), []), cluster.get("event_ids") or [])
            evidence_ids = _union(
                json_loads(existing.get("evidence_ids"), []), cluster.get("evidence_ids") or []
            )
            self.db.execute(
                "UPDATE clusters SET correlation_id = COALESCE(?, correlation_id), "
                "resource_id = COALESCE(?, resource_id), rule = COALESCE(?, rule), "
                "window_start = COALESCE(?, window_start), window_end = COALESCE(?, window_end), "
                "status = COALESCE(?, status), event_ids = ?, evidence_ids = ?, summary = COALESCE(?, summary), "
                "updated_at = ? WHERE cluster_id = ?",
                (
                    cluster.get("correlation_id"),
                    cluster.get("resource_id"),
                    cluster.get("rule"),
                    cluster.get("window_start"),
                    cluster.get("window_end"),
                    cluster.get("status"),
                    json_dumps(event_ids),
                    json_dumps(evidence_ids),
                    cluster.get("summary"),
                    now,
                    existing["cluster_id"],
                ),
            )
            self._attach_evidence(existing["cluster_id"], cluster.get("evidence_ids") or [])
            return existing["cluster_id"], False
        cluster_id = cluster.get("cluster_id") or new_id("clu")
        self.db.execute(
            "INSERT INTO clusters (cluster_id, cluster_key, correlation_id, resource_id, rule, window_start, "
            "window_end, status, event_ids, evidence_ids, summary, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",  # noqa: E501
            (
                cluster_id,
                key,
                cluster.get("correlation_id"),
                cluster.get("resource_id"),
                cluster.get("rule"),
                cluster.get("window_start"),
                cluster.get("window_end"),
                cluster.get("status") or "open",
                json_dumps(cluster.get("event_ids") or []),
                json_dumps(cluster.get("evidence_ids") or []),
                cluster.get("summary"),
                now,
                now,
            ),
        )
        self._attach_evidence(cluster_id, cluster.get("evidence_ids") or [])
        return cluster_id, True

    def _attach_evidence(self, cluster_id: str, evidence_ids: List[str]) -> None:
        ids = [evidence_id for evidence_id in evidence_ids if evidence_id]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        self.db.execute(
            "UPDATE evidence SET cluster_id = ? WHERE evidence_id IN (%s)" % placeholders,
            [cluster_id] + ids,
        )

    def get(self, cluster_id: str) -> Optional[Dict[str, Any]]:
        return self._decorate(
            self.db.query_one("SELECT * FROM clusters WHERE cluster_id = ?", (cluster_id,))
        )

    def query(
        self,
        correlation_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        rule: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        for column, value in (
            ("correlation_id", correlation_id),
            ("resource_id", resource_id),
            ("rule", rule),
            ("status", status),
        ):
            if value:
                clauses.append("%s = ?" % column)
                params.append(value)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([max(1, min(int(limit or 200), 2000)), max(0, int(offset or 0))])
        rows = self.db.query(
            "SELECT * FROM clusters%s ORDER BY updated_at DESC LIMIT ? OFFSET ?" % where,
            params,
        )
        return [self._decorate(row) for row in rows]

    def set_status(self, cluster_id: str, status: str) -> None:
        self.db.execute(
            "UPDATE clusters SET status = ?, updated_at = ? WHERE cluster_id = ?",
            (status, format_rfc3339(now_utc()), cluster_id),
        )

    @staticmethod
    def _decorate(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        row = dict(row)
        row["event_ids"] = json_loads(row.get("event_ids"), [])
        row["evidence_ids"] = json_loads(row.get("evidence_ids"), [])
        return row


def _build_evidence_where(
    cluster_id: Optional[str],
    correlation_id: Optional[str],
    resource_id: Optional[str],
    signal: Optional[str],
    kind: Optional[str],
    from_ts: Optional[str],
    to_ts: Optional[str],
) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    for column, value in (
        ("cluster_id", cluster_id),
        ("correlation_id", correlation_id),
        ("resource_id", resource_id),
        ("signal", signal),
        ("kind", kind),
    ):
        if value:
            clauses.append("%s = ?" % column)
            params.append(value)
    if from_ts:
        clauses.append("observed_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("observed_at <= ?")
        params.append(to_ts)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _union(left: List[Any], right: Iterable[Any]) -> List[Any]:
    merged = list(left or [])
    seen = set(merged)
    for item in right or []:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged
