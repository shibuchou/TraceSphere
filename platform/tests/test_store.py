import unittest

from tests.common import TempDB, PLATFORM_ROOT  # noqa: F401

from tsplatform.db import Database
from tsplatform.store_agents import AgentStore
from tsplatform.store_events import EventStore
from tsplatform.store_evidence import ClusterStore, EvidenceStore
from tsplatform.store_resources import ResourceStore
from tsplatform.util import format_rfc3339, now_utc


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = TempDB()
        self.db_path = self.temp.__enter__()
        self.db = Database(self.db_path)
        self.db.init()
        self.resources = ResourceStore(self.db)
        self.events = EventStore(self.db)
        self.evidence = EvidenceStore(self.db)
        self.clusters = ClusterStore(self.db)
        self.agents = AgentStore(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.__exit__(None, None, None)

    def test_resource_upsert_merges_attributes(self):
        self.resources.upsert(
            {"resource_id": "vm:x", "kind": "vm", "name": "vm-x", "attributes": {"a": 1}, "labels": {"l": "1"}}
        )
        self.resources.upsert({"resource_id": "vm:x", "kind": "vm", "attributes": {"b": 2}, "labels": {"m": "2"}})
        row = self.resources.get("vm:x")
        self.assertEqual(row["name"], "vm-x")
        self.assertEqual(row["attributes"], {"a": 1, "b": 2})
        self.assertEqual(row["labels"], {"l": "1", "m": "2"})

    def test_get_by_uuid_and_filters(self):
        self.resources.upsert({"resource_id": "vm:abc", "kind": "vm", "name": "vm-a", "cluster_id": "cluster:c1"})
        self.resources.upsert({"resource_id": "host:h1", "kind": "host", "name": "host-a"})
        self.assertIsNotNone(self.resources.get_by_uuid("abc"))
        self.assertIsNone(self.resources.get_by_uuid("nope"))
        self.assertEqual(self.resources.count(kind="vm"), 1)
        self.assertEqual(self.resources.count(kind="host"), 1)
        self.assertEqual(len(self.resources.list(kind="vm")), 1)
        self.assertEqual(len(self.resources.list(cluster_id="cluster:c1")), 1)
        self.assertEqual(len(self.resources.list(q="host-a")), 1)

    def test_edges_and_subgraph(self):
        self.resources.upsert({"resource_id": "vm:x", "kind": "vm", "name": "vm"})
        self.resources.upsert({"resource_id": "container:c1", "kind": "container", "name": "c1", "vm_id": "vm:x"})
        self.resources.upsert_edge({"src_id": "vm:x", "dst_id": "container:c1", "relation": "contains"})
        edges = self.resources.edges("vm:x")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["direction"], "out")
        graph = self.resources.subgraph("vm:x", depth=1)
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(len(graph["edges"]), 1)
        incoming = self.resources.subgraph("container:c1", depth=1, direction="in")
        self.assertEqual({node["resource_id"] for node in incoming["nodes"]}, {"container:c1", "vm:x"})
        placeholder = self.resources.subgraph("vm:x", depth=2)
        ids = {node["resource_id"] for node in placeholder["nodes"]}
        self.assertIn("container:c1", ids)

    def test_event_insert_dedup_and_query(self):
        observed = format_rfc3339(now_utc())
        base = {
            "schema_version": "v1",
            "origin": "app",
            "mode": "mock",
            "observed_at": observed,
            "type": "event",
            "event_type": "task.failed",
            "resource_id": "service:agent-service",
            "correlation_id": "corr-1",
            "task_id": "task-1",
            "severity": "major",
            "payload": {"status": "error"},
        }
        event_id, inserted = self.events.insert(base, dedup_key="k1")
        self.assertTrue(inserted)
        again_id, inserted_again = self.events.insert(base, dedup_key="k1")
        self.assertFalse(inserted_again)
        self.assertEqual(event_id, again_id)
        found = self.events.query(correlation_id="corr-1")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["payload"]["status"], "error")
        self.assertEqual(self.events.count(event_type="task.failed"), 1)
        self.events.set_cluster([event_id], "clu-1")
        self.assertEqual(self.events.get(event_id)["cluster_id"], "clu-1")

    def test_evidence_and_cluster_union(self):
        observed = format_rfc3339(now_utc())
        evidence_id, inserted = self.evidence.insert(
            {
                "kind": "cgroup",
                "signal": "memory.events.oom_kill",
                "resource_id": "container:c1",
                "observed_at": observed,
                "source_event_ids": ["evt-1"],
                "payload": {"delta": 1},
            },
            dedup_key="e1",
        )
        self.assertTrue(inserted)
        _, inserted_again = self.evidence.insert(
            {"kind": "cgroup", "signal": "memory.events.oom_kill", "observed_at": observed},
            dedup_key="e1",
        )
        self.assertFalse(inserted_again)
        cluster_id, created = self.clusters.upsert(
            {"cluster_key": "ck-1", "correlation_id": "corr-1", "event_ids": ["evt-1"], "evidence_ids": [evidence_id]}
        )
        self.assertTrue(created)
        same_id, created_again = self.clusters.upsert(
            {"cluster_key": "ck-1", "event_ids": ["evt-2"], "evidence_ids": []}
        )
        self.assertFalse(created_again)
        self.assertEqual(cluster_id, same_id)
        cluster = self.clusters.get(cluster_id)
        self.assertEqual(set(cluster["event_ids"]), {"evt-1", "evt-2"})
        self.assertEqual(cluster["evidence_ids"], [evidence_id])
        items = self.evidence.query(cluster_id=cluster_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_event_ids"], ["evt-1"])

    def test_agent_upsert_updates_last_seen(self):
        first = self.agents.upsert(
            {"agent_id": "a1", "configured_vm_uuid": "vm-uuid", "resource_id": "vm:vm-uuid", "hostname": "h1", "ips": ["1.2.3.4"]}
        )
        second = self.agents.upsert({"agent_id": "a1", "hostname": "h2"})
        self.assertEqual(first["registered_at"], second["registered_at"])
        self.assertEqual(second["hostname"], "h2")
        self.assertEqual(second["ips"], ["1.2.3.4"])
        self.assertEqual(self.agents.get_by_vm_uuid("vm-uuid")["agent_id"], "a1")


if __name__ == "__main__":
    unittest.main()
