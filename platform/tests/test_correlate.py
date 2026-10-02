import hashlib
import unittest

from tests.common import TempDB, PLATFORM_ROOT  # noqa: F401

from tsplatform.correlate import RULE_CORRELATION_ID, RULE_RESOURCE_WINDOW, CorrelationEngine
from tsplatform.db import Database
from tsplatform.ingest import EventIngest
from tsplatform.store_events import EventStore
from tsplatform.store_evidence import ClusterStore, EvidenceStore
from tsplatform.store_resources import ResourceStore


class CorrelateTest(unittest.TestCase):
    def setUp(self):
        self.temp = TempDB()
        self.db = Database(self.temp.__enter__())
        self.db.init()
        self.resources = ResourceStore(self.db)
        self.events = EventStore(self.db)
        self.evidence = EvidenceStore(self.db)
        self.clusters = ClusterStore(self.db)
        self.ingest = EventIngest(self.resources, self.events)
        self.engine = CorrelationEngine(self.events, self.resources, self.evidence, self.clusters, window_seconds=10)
        self.container = hashlib.sha256(b"c1").hexdigest()
        self._seed_case1()

    def tearDown(self):
        self.db.close()
        self.temp.__exit__(None, None, None)

    def _seed_case1(self):
        self.ingest.ingest_many(
            [
                {
                    "schema_version": "v1",
                    "origin": "cgroup",
                    "mode": "mock",
                    "observed_at": "2026-09-20T08:00:00Z",
                    "event_type": "memory.current",
                    "resource_id": "container:%s" % self.container,
                    "source": "vm-agent",
                    "payload": {"current": 104000000, "max": 104857600, "ratio": 0.99},
                },
                {
                    "schema_version": "v1",
                    "origin": "cgroup",
                    "mode": "mock",
                    "observed_at": "2026-09-20T08:00:02Z",
                    "event_type": "memory.events.oom_kill",
                    "resource_id": "container:%s" % self.container,
                    "source": "vm-agent",
                    "payload": {"delta": 1},
                },
                {
                    "event_type": "task.started",
                    "task_id": "task-1",
                    "correlation_id": "corr-1",
                    "service": "agent-service",
                    "timestamp": "2026-09-20T08:00:01Z",
                    "status": "ok",
                },
                {
                    "event_type": "task.failed",
                    "task_id": "task-1",
                    "correlation_id": "corr-1",
                    "service": "agent-service",
                    "timestamp": "2026-09-20T08:00:03Z",
                    "status": "error",
                    "attributes": {"container_id": self.container},
                },
            ],
            default_origin="app",
            default_mode="mock",
            default_source="test",
        )

    def test_case1_cluster_links_app_and_system_signals(self):
        result = self.engine.correlate(from_ts="2026-09-20T07:59:00Z", to_ts="2026-09-20T08:01:00Z")
        self.assertEqual(result["stats"]["clusters"], 1)
        cluster = result["clusters"][0]
        self.assertEqual(cluster["rule"], RULE_CORRELATION_ID)
        self.assertEqual(cluster["correlation_id"], "corr-1")
        signals = {item["signal"] for item in cluster["evidence"]}
        self.assertIn("memory.events.oom_kill", signals)
        self.assertIn("task.failed", signals)
        self.assertGreaterEqual(len(cluster["evidence"]), 3)
        for item in cluster["evidence"]:
            self.assertEqual(item["cluster_id"], cluster["cluster_id"])
        self.assertTrue(any(item["signal"] == "topology.adjacency" for item in cluster["evidence"]))
        stored_event = self.events.query(event_type="memory.current")[0]
        self.assertEqual(stored_event["cluster_id"], cluster["cluster_id"])

    def test_correlation_is_idempotent(self):
        first = self.engine.correlate(from_ts="2026-09-20T07:59:00Z", to_ts="2026-09-20T08:01:00Z")
        second = self.engine.correlate(from_ts="2026-09-20T07:59:00Z", to_ts="2026-09-20T08:01:00Z")
        self.assertEqual(len(first["clusters"]), len(second["clusters"]))
        self.assertEqual(
            first["clusters"][0]["cluster_id"], second["clusters"][0]["cluster_id"]
        )
        self.assertEqual(first["stats"]["evidence"], second["stats"]["evidence"])

    def test_resource_window_cluster_without_correlation_id(self):
        engine = CorrelationEngine(self.events, self.resources, self.evidence, self.clusters, window_seconds=10)
        self.ingest.ingest(
            {
                "schema_version": "v1",
                "origin": "ebpf",
                "mode": "mock",
                "observed_at": "2026-09-20T09:00:00Z",
                "event_type": "tcp.retransmit",
                "resource_id": "container:%s" % self.container,
                "payload": {"count": 3},
            }
        )
        result = engine.correlate(
            from_ts="2026-09-20T08:59:50Z",
            to_ts="2026-09-20T09:00:10Z",
            resource_id="container:%s" % self.container,
        )
        self.assertEqual(result["stats"]["clusters"], 1)
        cluster = result["clusters"][0]
        self.assertEqual(cluster["rule"], RULE_RESOURCE_WINDOW)
        self.assertEqual(cluster["resource_id"], "container:%s" % self.container)


if __name__ == "__main__":
    unittest.main()
