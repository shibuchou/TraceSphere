"""Agent registration store (方案 §5.5)."""

from typing import Any, Dict, List, Optional

from .db import Database
from .util import format_rfc3339, json_dumps, json_loads, now_utc


class AgentStore(object):
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, record: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = record.get("agent_id")
        if not agent_id:
            raise ValueError("agent registration requires agent_id")
        now = format_rfc3339(now_utc())
        ips = record.get("ips")
        ips_json = json_dumps(ips) if ips is not None else None
        existing = self.db.query_one("SELECT agent_id, registered_at FROM agents WHERE agent_id = ?", (agent_id,))
        if existing:
            self.db.execute(
                "UPDATE agents SET resource_id = COALESCE(?, resource_id), "
                "configured_vm_uuid = COALESCE(?, configured_vm_uuid), machine_id = COALESCE(?, machine_id), "
                "dmi_uuid = COALESCE(?, dmi_uuid), hostname = COALESCE(?, hostname), ips = COALESCE(?, ips), "
                "version = COALESCE(?, version), last_seen = ?, raw = ? WHERE agent_id = ?",
                (
                    record.get("resource_id"),
                    record.get("configured_vm_uuid"),
                    record.get("machine_id"),
                    record.get("dmi_uuid"),
                    record.get("hostname"),
                    ips_json,
                    record.get("version"),
                    now,
                    json_dumps(record.get("raw") or record),
                    agent_id,
                ),
            )
        else:
            self.db.execute(
                "INSERT INTO agents (agent_id, resource_id, configured_vm_uuid, machine_id, dmi_uuid, hostname, "
                "ips, version, registered_at, last_seen, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    record.get("resource_id"),
                    record.get("configured_vm_uuid"),
                    record.get("machine_id"),
                    record.get("dmi_uuid"),
                    record.get("hostname"),
                    ips_json if ips_json is not None else json_dumps([]),
                    record.get("version"),
                    now,
                    now,
                    json_dumps(record.get("raw") or record),
                ),
            )
        return self.get(agent_id)

    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self._decorate(self.db.query_one("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)))

    def get_by_vm_uuid(self, configured_vm_uuid: str) -> Optional[Dict[str, Any]]:
        row = self.db.query_one(
            "SELECT * FROM agents WHERE configured_vm_uuid = ? ORDER BY last_seen DESC LIMIT 1",
            (configured_vm_uuid,),
        )
        return self._decorate(row)

    def list(self) -> List[Dict[str, Any]]:
        return [
            self._decorate(row)
            for row in self.db.query("SELECT * FROM agents ORDER BY last_seen DESC")
        ]

    @staticmethod
    def _decorate(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        row = dict(row)
        row["ips"] = json_loads(row.get("ips"), [])
        row["raw"] = json_loads(row.get("raw"), {})
        return row
