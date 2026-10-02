import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from tests.common import WORKLOAD_VM_UUID, make_app, PLATFORM_ROOT  # noqa: F401

from tsplatform.api import serve


def _request(base_url, method, path, body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers=headers or {},
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return exc.code, json.loads(payload) if payload else {}


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="ts-api-test-")
        cls.app = make_app(db_path=cls.temp_dir + "/api.db")
        cls.sync_result = cls.app.sync()
        cls.server = serve(cls.app, "127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.close()

    def test_health_and_meta(self):
        status, payload = _request(self.base_url, "GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["provider"]["mode"], "mock")
        self.assertGreater(payload["database"]["counts"]["resources"], 5)
        status, meta = _request(self.base_url, "GET", "/api/v1/meta")
        self.assertEqual(status, 200)
        self.assertEqual(meta["schema_version"], "v1")
        self.assertIn("evidence", meta["types"])

    def test_resources_and_graph(self):
        status, payload = _request(self.base_url, "GET", "/api/v1/resources?kind=vm")
        self.assertEqual(status, 200)
        self.assertEqual(payload["total"], 1)
        vm_id = payload["resources"][0]["resource_id"]
        self.assertEqual(vm_id, "vm:%s" % WORKLOAD_VM_UUID)
        status, detail = _request(self.base_url, "GET", "/api/v1/resources/%s" % vm_id)
        self.assertEqual(status, 200)
        relations = {edge["relation"] for edge in detail["edges"]}
        self.assertIn("contains", relations)
        self.assertIn("attached_to", relations)
        status, graph = _request(self.base_url, "GET", "/api/v1/resources/%s/graph?depth=2" % vm_id)
        self.assertEqual(status, 200)
        kinds = {node["kind"] for node in graph["nodes"]}
        self.assertIn("host", kinds)
        self.assertIn("network", kinds)

    def test_agent_registration(self):
        status, payload = _request(
            self.base_url,
            "POST",
            "/api/v1/agents/register",
            {
                "agent_id": "vm-agent-test",
                "configured_vm_uuid": WORKLOAD_VM_UUID,
                "machine_id": "machine-1",
                "dmi_uuid": "dmi-1",
                "hostname": "workload-vm",
                "ips": ["10.0.0.10"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["resource_id"], "vm:%s" % WORKLOAD_VM_UUID)
        self.assertEqual(payload["vm"]["attributes"]["machine_id"], "machine-1")
        status, agents = _request(self.base_url, "GET", "/api/v1/agents")
        self.assertEqual(status, 200)
        self.assertEqual(agents["count"], 1)

    def test_event_ingest_correlate_evidence_context(self):
        status, payload = _request(
            self.base_url,
            "POST",
            "/api/v1/events",
            {
                "events": [
                    {
                        "schema_version": "v1",
                        "origin": "cgroup",
                        "mode": "mock",
                        "observed_at": "2026-09-20T08:00:00Z",
                        "event_type": "memory.events.oom_kill",
                        "resource_id": "container:api-test",
                        "payload": {"delta": 1},
                    },
                    {
                        "event_type": "task.failed",
                        "task_id": "task-api-1",
                        "correlation_id": "corr-api-1",
                        "service": "agent-service",
                        "timestamp": "2026-09-20T08:00:01Z",
                        "status": "error",
                    },
                ]
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["inserted"], 2)

        status, events = _request(self.base_url, "GET", "/api/v1/events?correlation_id=corr-api-1")
        self.assertEqual(status, 200)
        self.assertEqual(events["total"], 1)

        status, correlated = _request(
            self.base_url,
            "POST",
            "/api/v1/correlate",
            {"from": "2026-09-20T07:59:00Z", "to": "2026-09-20T08:01:00Z", "window_seconds": 30},
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(correlated["stats"]["clusters"], 1)
        cluster_id = correlated["clusters"][0]["cluster_id"]

        status, evidence = _request(self.base_url, "GET", "/api/v1/evidence?correlation_id=corr-api-1")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(evidence["total"], 1)

        status, cluster = _request(self.base_url, "GET", "/api/v1/clusters/%s" % cluster_id)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(cluster["evidence"]), 1)

        status, context = _request(
            self.base_url,
            "GET",
            "/api/v1/context?correlation_id=corr-api-1"
            "&from=2026-09-20T07:59:00Z&to=2026-09-20T08:01:00Z",
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(context["evidence"]), 1)
        self.assertGreaterEqual(len(context["events"]), 1)

    def test_errors(self):
        status, payload = _request(self.base_url, "GET", "/api/v1/nope")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")
        status, payload = _request(self.base_url, "GET", "/api/v1/events?limit=abc")
        self.assertEqual(status, 400)
        status, payload = _request(self.base_url, "GET", "/api/v1/resources/does-not-exist")
        self.assertEqual(status, 404)


class TokenAuthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="ts-api-auth-")
        cls.app = make_app(db_path=cls.temp_dir + "/auth.db", token="secret-token")
        cls.server = serve(cls.app, "127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.app.close()

    def test_health_open_but_api_requires_token(self):
        status, _ = _request(self.base_url, "GET", "/api/v1/health")
        self.assertEqual(status, 200)
        status, payload = _request(self.base_url, "GET", "/api/v1/resources")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "unauthorized")
        status, payload = _request(
            self.base_url, "GET", "/api/v1/resources", headers={"Authorization": "Bearer secret-token"}
        )
        self.assertEqual(status, 200)
        status, payload = _request(
            self.base_url, "GET", "/api/v1/resources", headers={"X-API-Token": "secret-token"}
        )
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
