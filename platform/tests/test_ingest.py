import hashlib
import unittest

from tests.common import TempDB, PLATFORM_ROOT  # noqa: F401

from tsplatform.db import Database
from tsplatform.ingest import EventIngest
from tsplatform.store_events import EventStore
from tsplatform.store_resources import ResourceStore


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.temp = TempDB()
        self.db = Database(self.temp.__enter__())
        self.db.init()
        self.resources = ResourceStore(self.db)
        self.events = EventStore(self.db)
        self.ingest = EventIngest(self.resources, self.events)
        self.container = hashlib.sha256(b"c1").hexdigest()

    def tearDown(self):
        self.db.close()
        self.temp.__exit__(None, None, None)

    def test_app_event_creates_identity_and_edges(self):
        result = self.ingest.ingest(
            {
                "event_type": "task.failed",
                "task_id": "task-1",
                "correlation_id": "corr-1",
                "service": "agent-service",
                "timestamp": "2026-09-20T08:00:00Z",
                "status": "error",
                "attributes": {"container_id": self.container},
            }
        )
        event = result["event"]
        self.assertEqual(event["resource_id"], "container:%s" % self.container)
        self.assertEqual(event["correlation_id"], "corr-1")
        self.assertEqual(event["severity"], "major")
        self.assertIsNotNone(self.resources.get("container:%s" % self.container))
        self.assertIsNotNone(self.resources.get("service:agent-service"))
        self.assertIsNotNone(self.resources.get("task:task-1"))
        task_edges = {(edge["src_id"], edge["dst_id"], edge["relation"]) for edge in self.resources.edges("task:task-1")}
        self.assertIn(("task:task-1", "service:agent-service", "runs_on"), task_edges)
        self.assertIn(("task:task-1", "container:%s" % self.container, "runs_on"), task_edges)
        service_edges = {(edge["src_id"], edge["dst_id"], edge["relation"]) for edge in self.resources.edges("service:agent-service")}
        self.assertIn(("service:agent-service", "container:%s" % self.container, "runs_on"), service_edges)

    def test_dedup_key_prevents_replay(self):
        raw = {
            "event_type": "zsvirt.alarm",
            "origin": "zsvirt",
            "timestamp": "2026-09-20T08:00:00Z",
            "dedup_key": "zsvirt:alarm:abc",
            "payload": {"uuid": "abc"},
        }
        first = self.ingest.ingest(raw)
        second = self.ingest.ingest(raw)
        self.assertTrue(first["inserted"])
        self.assertFalse(second["inserted"])
        self.assertEqual(self.events.count(), 1)

    def test_cgroup_event_keeps_resource_id(self):
        result = self.ingest.ingest(
            {
                "schema_version": "v1",
                "origin": "cgroup",
                "mode": "real",
                "observed_at": "2026-09-20T08:00:00Z",
                "type": "event",
                "event_type": "memory.events.oom_kill",
                "resource_id": "container:abc",
                "payload": {"delta": 1},
            },
            default_origin="cgroup",
        )
        event = result["event"]
        self.assertEqual(event["resource_id"], "container:abc")
        self.assertEqual(event["cluster_id"], None)
        self.assertIsNotNone(self.resources.get("container:abc"))

    def test_zsvirt_alarm_resolves_target_uuid(self):
        vm_uuid = "63bbb4613a524e4e97090600af03da93"
        self.resources.upsert({"resource_id": "vm:%s" % vm_uuid, "kind": "vm", "name": "workload-vm", "cluster_id": "cluster:c1"})
        result = self.ingest.ingest(
            {
                "schema_version": "v1",
                "origin": "zsvirt",
                "mode": "mock",
                "observed_at": "2026-09-20T08:00:00Z",
                "type": "alert",
                "event_type": "zsvirt.alarm",
                "severity": "critical",
                "payload": {"uuid": "alarm-1", "targetResourceUuid": vm_uuid},
                "dedup_key": "zsvirt:alarm:alarm-1",
            },
            default_origin="zsvirt",
        )
        self.assertEqual(result["event"]["resource_id"], "vm:%s" % vm_uuid)
        self.assertEqual(result["event"]["cluster_id"], "cluster:c1")

    def test_batch_summary(self):
        summary = self.ingest.ingest_many(
            [
                {"event_type": "task.started", "task_id": "t1", "timestamp": "2026-09-20T08:00:00Z"},
                {"event_type": "task.finished", "task_id": "t1", "timestamp": "2026-09-20T08:00:01Z"},
            ]
        )
        self.assertEqual(summary["inserted"], 2)
        self.assertEqual(len(summary["event_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
