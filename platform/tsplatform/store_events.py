"""Event store (Schema v1 events in SQLite WAL)."""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .db import Database
from .util import format_rfc3339, json_dumps, json_loads, new_id, now_utc

_FILTER_COLUMNS = {
    "resource_id": "resource_id",
    "correlation_id": "correlation_id",
    "task_id": "task_id",
    "event_type": "event_type",
    "type": "type",
    "severity": "severity",
    "cluster_id": "cluster_id",
    "origin": "origin",
    "mode": "mode",
    "source": "source",
}


class EventStore(object):
    def __init__(self, db: Database):
        self.db = db

    # ----- writes ---------------------------------------------------------
    def insert(self, event: Dict[str, Any], dedup_key: Optional[str] = None) -> Tuple[str, bool]:
        """Insert an event; returns ``(event_id, inserted)``.

        ``dedup_key`` deduplicates replayed sources (e.g. repeated ZSvirt syncs).
        """
        event_id = event.get("event_id") or new_id("evt")
        key = dedup_key if dedup_key is not None else event.get("dedup_key")
        if key:
            existing = self.db.query_one("SELECT event_id FROM events WHERE dedup_key = ?", (key,))
            if existing:
                return existing["event_id"], False
        now = format_rfc3339(now_utc())
        self.db.execute(
            "INSERT INTO events (event_id, schema_version, origin, mode, observed_at, ingested_at, type, "
            "event_type, resource_id, correlation_id, trace_id, task_id, severity, cluster_id, source, payload, dedup_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                event.get("schema_version") or "v1",
                event.get("origin") or "unknown",
                event.get("mode") or "real",
                event.get("observed_at") or now,
                event.get("ingested_at") or now,
                event.get("type") or "event",
                event.get("event_type") or "unknown",
                event.get("resource_id"),
                event.get("correlation_id"),
                event.get("trace_id"),
                event.get("task_id"),
                event.get("severity"),
                event.get("cluster_id"),
                event.get("source"),
                json_dumps(event.get("payload") or {}),
                key,
            ),
        )
        return event_id, True

    def insert_many(self, events: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        inserted = 0
        duplicates = 0
        event_ids: List[str] = []
        with self.db.tx():
            for event in events:
                event_id, is_new = self.insert(event)
                event_ids.append(event_id)
                if is_new:
                    inserted += 1
                else:
                    duplicates += 1
        return {"inserted": inserted, "duplicates": duplicates, "event_ids": event_ids}

    def set_cluster(self, event_ids: Sequence[str], cluster_id: str) -> int:
        if not event_ids:
            return 0
        placeholders = ",".join("?" for _ in event_ids)
        return self.db.execute(
            "UPDATE events SET cluster_id = ? WHERE event_id IN (%s)" % placeholders,
            [cluster_id] + list(event_ids),
        )

    # ----- reads ----------------------------------------------------------
    def get(self, event_id: str) -> Optional[Dict[str, Any]]:
        return self._decorate(
            self.db.query_one("SELECT * FROM events WHERE event_id = ?", (event_id,))
        )

    def query(
        self,
        from_ts: Optional[str] = None,
        to_ts: Optional[str] = None,
        order: str = "asc",
        limit: int = 500,
        offset: int = 0,
        **filters: Any
    ) -> List[Dict[str, Any]]:
        where, params = _build_where(from_ts, to_ts, filters)
        direction = "DESC" if str(order).lower() == "desc" else "ASC"
        params.extend([max(1, min(int(limit or 500), 5000)), max(0, int(offset or 0))])
        rows = self.db.query(
            "SELECT * FROM events%s ORDER BY observed_at %s, event_id %s LIMIT ? OFFSET ?"
            % (where, direction, direction),
            params,
        )
        return [self._decorate(row) for row in rows]

    def count(self, from_ts: Optional[str] = None, to_ts: Optional[str] = None, **filters: Any) -> int:
        where, params = _build_where(from_ts, to_ts, filters)
        return int(self.db.scalar("SELECT COUNT(*) FROM events%s" % where, params) or 0)

    def distinct_clusters(self, **filters: Any) -> List[str]:
        where, params = _build_where(None, None, filters)
        rows = self.db.query(
            "SELECT DISTINCT cluster_id FROM events%s AND cluster_id IS NOT NULL" % where,
            params,
        )
        return [row["cluster_id"] for row in rows]

    @staticmethod
    def _decorate(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        row = dict(row)
        row["payload"] = json_loads(row.get("payload"), {})
        return row


def _build_where(from_ts: Optional[str], to_ts: Optional[str], filters: Dict[str, Any]) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    if from_ts:
        clauses.append("observed_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("observed_at <= ?")
        params.append(to_ts)
    for key, column in _FILTER_COLUMNS.items():
        value = filters.get(key)
        if value:
            clauses.append("%s = ?" % column)
            params.append(value)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
