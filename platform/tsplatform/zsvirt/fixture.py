"""FixtureProvider: replay official/real ZSvirt REST responses.

Fixture files store raw ZStack responses exactly as returned by the API
(方案 §4.2). The same mapper as RESTProvider converts them into the domain
model, so upper layers cannot tell the two providers apart.

Optional scenarios: ``fixtures/<scenario>/vms.json`` overrides
``fixtures/vms.json`` file by file (normal / faulty / degraded demos).
"""

import json
import os
from typing import Any, Dict, List, Optional

from ..util import format_rfc3339
from .base import Snapshot, ZSvirtProvider
from .mapper import snapshot_from_raw

FIXTURE_FILES = {
    "zones": "zones",
    "clusters": "clusters",
    "hosts": "hosts",
    "vms": "vms",
    "images": "images",
    "l3_networks": "l3-networks",
    "l2_networks": "l2-networks",
    "port_groups": "port-groups",
    "primary_storages": "primary-storages",
    "backup_storages": "backup-storages",
    "instance_offerings": "instance-offerings",
    "alarms": "alerts",
    "events": "events",
}


class FixtureProvider(ZSvirtProvider):
    name = "fixture"
    mode = "mock"

    def __init__(self, fixtures_dir: str, scenario: Optional[str] = None):
        self.fixtures_dir = fixtures_dir
        self.scenario = scenario
        self.missing: List[str] = []

    def _resolve(self, filename: str) -> Optional[str]:
        if self.scenario:
            scoped = os.path.join(self.fixtures_dir, self.scenario, filename + ".json")
            if os.path.isfile(scoped):
                return scoped
        base = os.path.join(self.fixtures_dir, filename + ".json")
        return base if os.path.isfile(base) else None

    def load_raw(self) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        self.missing = []
        for logical, filename in FIXTURE_FILES.items():
            path = self._resolve(filename)
            if path is None:
                self.missing.append(filename)
                raw[logical] = None
                continue
            with open(path, "r", encoding="utf-8") as handle:
                raw[logical] = json.load(handle)
        return raw

    def load_meta(self) -> Dict[str, Any]:
        path = self._resolve("_capture")
        if not path:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def snapshot(self) -> Snapshot:
        raw = self.load_raw()
        meta = self.load_meta()
        snapshot = snapshot_from_raw(
            raw,
            mode=self.mode,
            provider=self.name,
            captured_at=meta.get("captured_at") or format_rfc3339(),
        )
        if self.missing:
            snapshot.errors["missing_fixtures"] = ",".join(self.missing)
        return snapshot

    @property
    def description(self) -> str:
        suffix = "/%s" % self.scenario if self.scenario else ""
        return "fixture%s (%s)" % (suffix, self.fixtures_dir)
