import unittest

from tests.common import FIXTURES_DIR, PLATFORM_ROOT, TempDB, make_config  # noqa: F401

from tsplatform.app import PlatformApp
from tsplatform.zsvirt import FixtureProvider
from tsplatform.zsvirt.mapper import (
    alarm_inventories_to_events,
    zsvirt_event_inventories_to_events,
)


class ZSvirtAlarmEventTest(unittest.TestCase):
    """Locks the real /zwatch/alarms and /zwatch/events response shapes."""

    @classmethod
    def setUpClass(cls):
        cls.snapshot = FixtureProvider(FIXTURES_DIR).snapshot()
        cls.expected_active = sum(
            1
            for alarm in cls.snapshot.alarms
            if (alarm.get("status") or "").lower() == "alarm"
        )

    def test_only_active_alarms_become_events(self):
        events = alarm_inventories_to_events(self.snapshot.alarms, mode="mock")
        self.assertEqual(len(events), self.expected_active)
        self.assertGreaterEqual(self.expected_active, 1)
        for event in events:
            self.assertEqual(event["event_type"], "zsvirt.alarm")
            self.assertEqual(event["type"], "alert")
            self.assertEqual((event["payload"].get("status") or "").lower(), "alarm")
            self.assertIn(event["severity"], ("warning", "major", "critical"))
            self.assertTrue(event["dedup_key"].startswith("zsvirt:alarm:"))

    def test_all_alarms_mode_keeps_definitions(self):
        events = alarm_inventories_to_events(self.snapshot.alarms, mode="mock", active_only=False)
        self.assertEqual(len(events), len(self.snapshot.alarms))
        self.assertGreaterEqual(len(events), self.expected_active)

    def test_zwatch_event_shape(self):
        events = zsvirt_event_inventories_to_events(self.snapshot.events, mode="mock")
        self.assertEqual(len(events), len(self.snapshot.events))
        if not events:
            self.skipTest("no /zwatch/events captured")
        first = events[0]
        self.assertEqual(first["event_type"], "zsvirt.event")
        self.assertEqual(first["type"], "event")
        self.assertEqual(first["severity"], "info")
        self.assertTrue(first["observed_at"].endswith("Z"))
        self.assertIn("name", first["payload"])
        self.assertTrue(first["dedup_key"].startswith("zsvirt:event:"))

    def test_sync_ingests_and_dedups_real_events(self):
        with TempDB() as db_path:
            cfg = make_config(db_path)
            app = PlatformApp(cfg, provider=FixtureProvider(FIXTURES_DIR))
            try:
                result = app.sync()
                self.assertTrue(result.ok, result.errors)
                self.assertEqual(app.events.count(event_type="zsvirt.alarm"), self.expected_active)
                self.assertEqual(app.events.count(event_type="zsvirt.event"), len(self.snapshot.events))

                second = app.sync()
                self.assertEqual(second.events_ingested, 0)
                self.assertEqual(
                    second.events_duplicated,
                    self.expected_active + len(self.snapshot.events),
                )
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
