import json
import os
import unittest

from tests.common import (
    CLUSTER_UUID,
    FIXTURES_DIR,
    HOST_UUID,
    L3_UUID,
    PLATFORM_ROOT,  # noqa: F401
    WORKLOAD_VM_UUID,
    ZONE_UUID,
)

from tsplatform.zsvirt import FixtureProvider
from tsplatform.zsvirt.mapper import snapshot_from_raw


def _load(name):
    with open(os.path.join(FIXTURES_DIR, name + ".json"), "r", encoding="utf-8") as handle:
        return json.load(handle)


class FixtureProviderTest(unittest.TestCase):
    def setUp(self):
        self.provider = FixtureProvider(FIXTURES_DIR)

    def test_snapshot_mode_and_counts(self):
        snapshot = self.provider.snapshot()
        self.assertEqual(snapshot.mode, "mock")
        self.assertEqual(snapshot.provider, "fixture")
        self.assertEqual(self.provider.missing, [])
        self.assertGreaterEqual(len(snapshot.resources), 10)
        self.assertGreaterEqual(len(snapshot.edges), 8)

    def test_vm_resource_from_fixture(self):
        snapshot = self.provider.snapshot()
        by_id = {record.resource_id: record for record in snapshot.resources}
        vm = by_id["vm:%s" % WORKLOAD_VM_UUID]
        self.assertEqual(vm.kind, "vm")
        self.assertEqual(vm.name, "workload-vm")
        self.assertEqual(vm.state, "Running")
        self.assertEqual(vm.host_id, "host:%s" % HOST_UUID)
        self.assertEqual(vm.cluster_id, "cluster:%s" % CLUSTER_UUID)
        self.assertEqual(vm.zone_id, "zone:%s" % ZONE_UUID)
        self.assertEqual(vm.attributes["cpuNum"], 4)
        self.assertEqual(vm.attributes["memorySize"], 4294967296)
        # ZSvirt does not record the guest IP (flat DHCP provided by the host);
        # the IP is merged in from Agent Registration attributes instead
        self.assertEqual(vm.attributes["ips"], [])
        self.assertEqual(vm.attributes["macs"], ["fa:6f:c9:04:b0:00"])

    def test_expected_edges(self):
        snapshot = self.provider.snapshot()
        edges = {(edge.src_id, edge.dst_id, edge.relation) for edge in snapshot.edges}
        self.assertIn(("host:%s" % HOST_UUID, "vm:%s" % WORKLOAD_VM_UUID, "contains"), edges)
        self.assertIn(("cluster:%s" % CLUSTER_UUID, "host:%s" % HOST_UUID, "contains"), edges)
        self.assertIn(("zone:%s" % ZONE_UUID, "cluster:%s" % CLUSTER_UUID, "contains"), edges)
        self.assertIn(("vm:%s" % WORKLOAD_VM_UUID, "network:%s" % L3_UUID, "attached_to"), edges)
        self.assertIn(("vm:%s" % WORKLOAD_VM_UUID, "image:f39ba0991de143e6b76b0887e19edb0a", "uses"), edges)
        self.assertIn(("vm:%s" % WORKLOAD_VM_UUID, "volume:c6114309f9d34fa980a00a4895383654", "has_volume"), edges)
        self.assertIn(("volume:c6114309f9d34fa980a00a4895383654", "datastore:4a0ecf3f472c4042aa4f9f9d36494b11", "assigned_to"), edges)
        # pg-demo is a portGroup on the L2PortGroup 04eb58aa (real hierarchy)
        self.assertIn(("network:%s" % L3_UUID, "network:04eb58aa1a704dd3ab227bd3de1ee786", "over"), edges)
        self.assertIn(("network:04eb58aa1a704dd3ab227bd3de1ee786", "network:db58a900bd344ba8ba6904ff7b7ce9e9", "over"), edges)

    def test_scenario_override(self):
        import tempfile

        scoped = tempfile.mkdtemp(prefix="ts-fixture-scenario-")
        try:
            os.makedirs(os.path.join(scoped, "faulty"))
            with open(os.path.join(scoped, "faulty", "hosts.json"), "w", encoding="utf-8") as handle:
                json.dump({"inventories": [], "total": 0}, handle)
            provider = FixtureProvider(scoped, scenario="faulty")
            snapshot = provider.snapshot()
            host_ids = [r.resource_id for r in snapshot.resources if r.kind == "host"]
            self.assertEqual(host_ids, [])
        finally:
            import shutil

            shutil.rmtree(scoped, ignore_errors=True)


class MapperEdgeCasesTest(unittest.TestCase):
    def test_missing_collections_are_tolerated(self):
        snapshot = snapshot_from_raw({"vms": _load("vms")}, mode="mock", provider="test")
        self.assertEqual(len(snapshot.resources), 2)  # vm + root volume
        vm = [r for r in snapshot.resources if r.kind == "vm"][0]
        # ids are carried by the VM inventory itself, even when sibling
        # collections are missing; the referenced resources stay unmapped
        self.assertEqual(vm.cluster_id, "cluster:%s" % CLUSTER_UUID)
        self.assertEqual(vm.host_id, "host:%s" % HOST_UUID)
        self.assertEqual([r for r in snapshot.resources if r.kind == "host"], [])
        edges = {(edge.src_id, edge.dst_id, edge.relation) for edge in snapshot.edges}
        self.assertIn(("host:%s" % HOST_UUID, "vm:%s" % WORKLOAD_VM_UUID, "contains"), edges)

    def test_alarm_inventories_preserved(self):
        snapshot = snapshot_from_raw(
            {"alarms": {"inventories": [{"uuid": "a-1", "name": "alarm"}], "total": 1}},
            mode="mock",
            provider="test",
        )
        self.assertEqual(len(snapshot.alarms), 1)


if __name__ == "__main__":
    unittest.main()
