"""Resource Registry: sync a ZSvirt provider snapshot into SQLite + graph.

The registry is the single write path for ZSvirt resources and edges
(方案 §5.5). It is idempotent: re-syncing the same snapshot only refreshes
``updated_at`` / ``observed_at``.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .db import Database
from .store_resources import ResourceStore
from .util import format_rfc3339, json_dumps, now_utc


@dataclass
class SyncResult:
    provider: str
    mode: str
    started_at: str
    finished_at: Optional[str] = None
    ok: bool = False
    resources: int = 0
    edges: int = 0
    events_ingested: int = 0
    events_duplicated: int = 0
    errors: Dict[str, str] = field(default_factory=dict)
    captured_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResourceRegistry(object):
    def __init__(
        self,
        db: Database,
        resources: ResourceStore,
        event_ingest: Optional[Any] = None,
    ):
        self.db = db
        self.resources = resources
        self.event_ingest = event_ingest
        self.last_result: Optional[SyncResult] = None

    def sync(self, provider: Any, ingest_events: bool = True) -> SyncResult:
        from .zsvirt.mapper import alarm_inventories_to_events, zsvirt_event_inventories_to_events

        started = format_rfc3339(now_utc())
        result = SyncResult(provider=provider.name, mode=provider.mode, started_at=started)
        # NOTE: 必须用 insert() 取 lastrowid；INSERT 无结果行，scalar() 会返回 None
        # 导致收尾 UPDATE 被跳过、sync_runs 永远停留在未完成状态。
        sync_id = self.db.insert(
            "INSERT INTO sync_runs (provider, mode, started_at, ok, counts, error) VALUES (?, ?, ?, 0, '{}', NULL)",
            (provider.name, provider.mode, started),
        )
        try:
            snapshot = provider.snapshot()
            result.captured_at = snapshot.captured_at
            result.errors.update(snapshot.errors or {})
            records = [asdict(record) for record in snapshot.resources]
            edges = [asdict(edge) for edge in snapshot.edges]
            result.resources = self.resources.upsert_many(records)
            result.edges = self.resources.upsert_edges(edges)

            if ingest_events and self.event_ingest is not None:
                raw_events = alarm_inventories_to_events(
                    snapshot.alarms, mode=snapshot.mode, fallback_time=snapshot.captured_at
                )
                raw_events += zsvirt_event_inventories_to_events(
                    snapshot.events, mode=snapshot.mode, fallback_time=snapshot.captured_at
                )
                summary = self.event_ingest.ingest_many(
                    raw_events,
                    default_origin="zsvirt",
                    default_mode=snapshot.mode,
                    default_source="zsvirt",
                )
                result.events_ingested = summary.get("inserted", 0)
                result.events_duplicated = summary.get("duplicates", 0)
                for item in summary.get("warnings", []):
                    result.errors.setdefault("events", item)

            result.ok = not result.errors or set(result.errors.keys()) == {"missing_fixtures"}
        except Exception as exc:  # noqa: BLE001 - recorded for /health visibility
            result.errors["sync"] = "%s: %s" % (type(exc).__name__, exc)
        result.finished_at = format_rfc3339(now_utc())
        counts = json_dumps(
            {
                "resources": result.resources,
                "edges": result.edges,
                "events_ingested": result.events_ingested,
                "events_duplicated": result.events_duplicated,
            }
        )
        error_text = json_dumps(result.errors) if result.errors else None
        if sync_id > 0:
            self.db.execute(
                "UPDATE sync_runs SET finished_at = ?, ok = ?, counts = ?, error = ? WHERE id = ?",
                (result.finished_at, 1 if result.ok else 0, counts, error_text, sync_id),
            )
        self.last_result = result
        return result

    def last_sync(self) -> Optional[Dict[str, Any]]:
        row = self.db.query_one("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
        if row:
            from .util import json_loads

            row["counts"] = json_loads(row.get("counts"), {})
            row["error"] = json_loads(row.get("error"), None)
        return row
