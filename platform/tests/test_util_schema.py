import unittest

from tests.common import PLATFORM_ROOT  # noqa: F401  (path bootstrap)

from tsplatform.schema import ValidationError, normalize_event
from tsplatform.util import (
    format_rfc3339,
    parse_timestamp,
    safe_severity,
    sha512_hex,
)


class TimestampTest(unittest.TestCase):
    def test_parse_rfc3339_z(self):
        dt = parse_timestamp("2026-09-20T08:00:00Z")
        self.assertEqual(format_rfc3339(dt), "2026-09-20T08:00:00.000Z")

    def test_parse_offset_normalizes_to_utc(self):
        dt = parse_timestamp("2026-09-18T20:00:03+08:00")
        self.assertEqual(format_rfc3339(dt), "2026-09-18T12:00:03.000Z")

    def test_parse_zstack_display_date(self):
        dt = parse_timestamp("Sep 17, 2026 10:00:00")
        self.assertEqual(format_rfc3339(dt), "2026-09-17T10:00:00.000Z")

    def test_parse_epoch_millis(self):
        dt = parse_timestamp(1758326400000)
        self.assertIsNotNone(dt)

    def test_invalid_returns_default(self):
        self.assertIsNone(parse_timestamp("not-a-date"))

    def test_sha512_matches_known_value(self):
        import hashlib

        self.assertEqual(
            sha512_hex("demo-password"),
            hashlib.sha512(b"demo-password").hexdigest(),
        )
        self.assertEqual(len(sha512_hex("demo-password")), 128)


class SchemaTest(unittest.TestCase):
    def test_app_event_normalized(self):
        event, warnings = normalize_event(
            {
                "event_type": "task.failed",
                "task_id": "task-1",
                "correlation_id": "corr-1",
                "service": "agent-service",
                "timestamp": "2026-09-18T20:00:03+08:00",
                "status": "timeout",
                "attributes": {"tool": "search", "duration_ms": 1500},
            }
        )
        self.assertEqual(event["schema_version"], "v1")
        self.assertEqual(event["origin"], "app")
        self.assertEqual(event["mode"], "real")
        self.assertEqual(event["type"], "event")
        self.assertEqual(event["event_type"], "task.failed")
        self.assertEqual(event["observed_at"], "2026-09-18T12:00:03.000Z")
        self.assertEqual(event["severity"], "major")
        self.assertEqual(event["correlation_id"], "corr-1")
        self.assertEqual(event["task_id"], "task-1")
        self.assertEqual(event["payload"]["status"], "timeout")
        self.assertEqual(event["payload"]["service"], "agent-service")
        self.assertEqual(event["payload"]["attributes"]["tool"], "search")
        self.assertEqual(warnings, [])

    def test_schema_v1_event_kept(self):
        event, _ = normalize_event(
            {
                "schema_version": "v1",
                "origin": "cgroup",
                "mode": "mock",
                "observed_at": "2026-09-20T01:02:03Z",
                "type": "event",
                "event_type": "memory.events.oom_kill",
                "resource_id": "container:abc",
                "severity": "critical",
                "payload": {"delta": 1},
            }
        )
        self.assertEqual(event["origin"], "cgroup")
        self.assertEqual(event["mode"], "mock")
        self.assertEqual(event["severity"], "critical")
        self.assertEqual(event["resource_id"], "container:abc")
        self.assertEqual(event["payload"], {"delta": 1})

    def test_loose_vm_agent_event_fields_go_to_payload(self):
        event, warnings = normalize_event(
            {
                "event_type": "oom_kill",
                "observed_at": "2026-09-20T01:02:03Z",
                "pid": 4242,
                "comm": "stress-ng",
                "cgroup": "/docker/abc",
                "container_id": "abc123",
            },
            default_origin="ebpf",
            default_source="vm-agent",
        )
        self.assertEqual(event["origin"], "ebpf")
        self.assertEqual(event["event_type"], "oom_kill")
        self.assertEqual(event["payload"]["pid"], 4242)
        self.assertEqual(event["payload"]["container_id"], "abc123")
        self.assertEqual(event["source"], "vm-agent")
        self.assertEqual(warnings, [])

    def test_alarm_event_type_maps_to_alert(self):
        event, _ = normalize_event(
            {"event_type": "zsvirt.alarm", "observed_at": "2026-09-20T01:02:03Z"},
            default_origin="zsvirt",
        )
        self.assertEqual(event["type"], "alert")

    def test_non_object_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_event(["not", "an", "object"])

    def test_severity_mapping(self):
        # ZStack emergency levels: Emergent > Important > Normal
        self.assertEqual(safe_severity("Emergent"), "critical")
        self.assertEqual(safe_severity("Important"), "major")
        self.assertEqual(safe_severity("Normal"), "info")
        self.assertEqual(safe_severity("Major"), "major")
        self.assertEqual(safe_severity("Minor"), "warning")
        self.assertIsNone(safe_severity("bogus"))


if __name__ == "__main__":
    unittest.main()
