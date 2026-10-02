import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from tests.common import PLATFORM_ROOT  # noqa: F401

from tsplatform.util import sha512_hex
from tsplatform.zsvirt import RESTProvider, ZSvirtError, ZSvirtRestClient

HOSTS = [
    {
        "uuid": "h-%d" % index,
        "name": "host-%d" % index,
        "clusterUuid": "c-1",
        "zoneUuid": "z-1",
        "state": "Enabled",
        "status": "Connected",
        "cpuNum": 8,
        "memorySize": 1073741824,
    }
    for index in range(3)
]
VM = {
    "uuid": "vm-1",
    "name": "vm-1",
    "state": "Running",
    "hostUuid": "h-0",
    "clusterUuid": "c-1",
    "zoneUuid": "z-1",
    "cpuNum": 2,
    "memorySize": 1024,
    "vmNics": [],
    "allVolumes": [],
}


class FakeState(object):
    def __init__(self):
        self.login_calls = 0
        self.password_hashes = []
        self.fail_next_get_401 = False
        self.get_requests = []


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            parsed = urlparse(self.path)
            if parsed.path == "/zstack/v1/accounts/login":
                state.login_calls += 1
                state.password_hashes.append((body.get("logInByAccount") or {}).get("password"))
                self._send(200, {"inventory": {"uuid": "sess-%d" % state.login_calls}})
                return
            self._send(404, {"error": {"code": "SYS.404", "description": "not found"}})

        def do_GET(self):
            parsed = urlparse(self.path)
            auth = self.headers.get("Authorization")
            state.get_requests.append((parsed.path, parsed.query, auth))
            if state.fail_next_get_401:
                state.fail_next_get_401 = False
                self._send(401, {"error": {"code": "SYS.1003", "description": "session expired"}})
                return
            if auth != "OAuth sess-%d" % state.login_calls:
                self._send(401, {"error": {"code": "SYS.1003", "description": "invalid session"}})
                return
            query = parse_qs(parsed.query)
            start = int(query.get("start", ["0"])[0])
            limit = int(query.get("limit", ["100"])[0])
            if parsed.path == "/zstack/v1/hosts":
                self._send(200, {"inventories": HOSTS[start:start + limit], "total": len(HOSTS)})
                return
            if parsed.path == "/zstack/v1/vm-instances":
                self._send(200, {"inventories": [VM][start:start + limit], "total": 1})
                return
            self._send(404, {"error": {"code": "SYS.404", "description": "not found"}})

    return Handler


class RestProviderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = FakeState()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.state))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d/zstack/v1" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.state.login_calls = 0
        self.state.password_hashes = []
        self.state.fail_next_get_401 = False
        self.state.get_requests = []

    def _client(self, **kwargs):
        return ZSvirtRestClient(self.base_url, "admin", "secret-pass", timeout=5, page_size=2, **kwargs)

    def test_login_hashes_password_and_sets_session(self):
        client = self._client()
        session = client.login()
        self.assertEqual(session, "sess-1")
        self.assertEqual(self.state.password_hashes, [sha512_hex("secret-pass")])

    def test_query_paginates_and_sends_oauth_header(self):
        client = self._client()
        client.login()
        page = client.query("hosts")
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["inventories"]), 3)
        starts = [parse_qs(query).get("start", ["?"])[0] for _, query, _ in self.state.get_requests]
        self.assertEqual(starts, ["0", "2"])
        for _, _, auth in self.state.get_requests:
            self.assertEqual(auth, "OAuth sess-1")

    def test_reauth_after_401(self):
        client = self._client()
        client.login()
        self.state.fail_next_get_401 = True
        page = client.query("hosts")
        self.assertEqual(len(page["inventories"]), 3)
        self.assertEqual(self.state.login_calls, 2)

    def test_error_raises_with_status_and_code(self):
        client = self._client()
        client.login()
        with self.assertRaises(ZSvirtError) as ctx:
            client.query("missing-collection")
        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(ctx.exception.code, "SYS.404")

    def test_rest_provider_partial_errors(self):
        client = self._client(paths={"hosts": "hosts", "vms": "vm-instances", "alarms": "missing"})
        provider = RESTProvider(client, include=["hosts", "vms", "alarms"])
        snapshot = provider.snapshot()
        kinds = sorted(record.kind for record in snapshot.resources)
        self.assertEqual(kinds, ["host", "host", "host", "vm"])
        self.assertIn("alarms", snapshot.errors)
        self.assertEqual(snapshot.mode, "real")
        vm = [record for record in snapshot.resources if record.kind == "vm"][0]
        self.assertEqual(vm.host_id, "host:h-0")
        self.assertEqual(vm.attributes["cpuNum"], 2)


if __name__ == "__main__":
    unittest.main()
