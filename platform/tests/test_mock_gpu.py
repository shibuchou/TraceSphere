import os
import tempfile
import unittest

from tsplatform import mockgpu
from tsplatform.db import Database
from tsplatform.store_resources import ResourceStore


class MockGpuTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.db.init()
        self.store = ResourceStore(self.db)
        self.store.upsert({"resource_id": "host:host-1", "kind": "host", "name": "host-1"})
        self.store.upsert(
            {
                "resource_id": "vm:vm-1",
                "kind": "vm",
                "name": "workload-vm",
                "host_id": "host:host-1",
            }
        )

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_disabled_by_default(self):
        self.assertIsNone(mockgpu.register_mock_gpu(self.store, {}))
        self.assertIsNone(
            mockgpu.register_mock_gpu(self.store, {"mock_gpu": {"enabled": False}})
        )

    def test_registers_resource_and_edges(self):
        rid = mockgpu.register_mock_gpu(
            self.store,
            {
                "mock_gpu": {
                    "enabled": True,
                    "uuid": "mock-gpu0",
                    "vm_uuid": "vm-1",
                    "memory_total_bytes": 8 * 1024 ** 3,
                }
            },
        )
        self.assertEqual(rid, "gpu:mock-gpu0")
        row = self.store.get("gpu:mock-gpu0")
        self.assertIsNotNone(row)
        self.assertEqual(row["kind"], "gpu")
        self.assertEqual(row["vm_id"], "vm:vm-1")
        self.assertEqual(row["mode"], "mock")

        edges = self.store.edges("gpu:mock-gpu0", direction="both")
        pairs = {(e["relation"], e["src_id"], e["dst_id"]) for e in edges}
        self.assertIn(("contains", "host:host-1", "gpu:mock-gpu0"), pairs)
        self.assertIn(("assigned_to", "gpu:mock-gpu0", "vm:vm-1"), pairs)

    def test_env_override_enables(self):
        os.environ["TRACESPHERE_MOCK_GPU"] = "1"
        try:
            from tsplatform.config import load_config

            cfg = load_config()
            self.assertTrue(cfg["mock_gpu"]["enabled"])
        finally:
            os.environ.pop("TRACESPHERE_MOCK_GPU", None)


if __name__ == "__main__":
    unittest.main()
