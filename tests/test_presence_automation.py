import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from interfaces.presence_automation import (
    PresenceAutomation,
    PresenceAutomationConfig,
)


class PresenceAutomationTest(unittest.TestCase):
    def _automation(self, directory, now, **overrides):
        values = {
            "enabled": True,
            "timezone_name": "Europe/Berlin",
            "weather_location": "Teststadt",
            "return_briefing_after": 900,
            "greeting_cooldown": 14_400,
            "state_path": Path(directory, "presence.json"),
        }
        values.update(overrides)
        announcements = []
        automation = PresenceAutomation(
            PresenceAutomationConfig(**values),
            weather_provider=lambda location: f"In {location} sind es 20 Grad.",
            announcer=announcements.append,
            clock=lambda: now[0],
        )
        return automation, announcements

    @staticmethod
    def _room(presence, identity=None):
        return {"sensor": "room", "presence": presence, "identity": identity}

    def test_initial_recognition_greets_once(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)]
            automation, announcements = self._automation(directory, now)

            self.assertEqual(
                automation.handle_report(self._room(True, "Tim")),
                "Hallo, Tim.",
            )
            self.assertIsNone(automation.handle_report(self._room(True, "Tim")))
            self.assertEqual(announcements, ["Hallo, Tim."])

    def test_short_absence_stays_silent(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)]
            automation, announcements = self._automation(directory, now)
            automation.handle_report(self._room(True, "Tim"))

            now[0] += timedelta(minutes=1)
            automation.handle_report(self._room(False))
            now[0] += timedelta(minutes=2)
            result = automation.handle_report(self._room(True, "Tim"))

            self.assertIsNone(result)
            self.assertEqual(announcements, ["Hallo, Tim."])

    def test_long_absence_reports_duration_and_events(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)]
            automation, announcements = self._automation(directory, now)
            automation.handle_report(self._room(True, "Tim"))
            now[0] += timedelta(minutes=1)
            automation.handle_report(self._room(False))
            self.assertTrue(automation.record_event("Die Waschmaschine ist fertig."))

            now[0] += timedelta(minutes=20)
            result = automation.handle_report(self._room(True, "Tim"))

            self.assertIn("Willkommen zurück, Tim.", result)
            self.assertIn("20 Minuten", result)
            self.assertIn("Die Waschmaschine ist fertig.", result)
            self.assertEqual(automation.status()["pending_event_count"], 0)
            self.assertEqual(announcements[-1], result)

    def test_morning_greeting_includes_weather_only_once_per_day(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)]
            automation, announcements = self._automation(directory, now)

            result = automation.handle_report(self._room(True, "Tim"))
            self.assertEqual(
                result,
                "Guten Morgen, Tim. In Teststadt sind es 20 Grad.",
            )
            automation.handle_report(self._room(False))
            now[0] += timedelta(minutes=2)
            self.assertIsNone(automation.handle_report(self._room(True, "Tim")))
            self.assertEqual(len(announcements), 1)

    def test_unknown_person_never_receives_announcement(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)]
            automation, announcements = self._automation(directory, now)

            self.assertIsNone(automation.handle_report(self._room(True)))
            self.assertEqual(announcements, [])

    def test_disabled_automation_does_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [datetime(2026, 8, 29, 6, 0, tzinfo=timezone.utc)]
            automation, announcements = self._automation(
                directory, now, enabled=False)

            self.assertIsNone(automation.handle_report(self._room(True, "Tim")))
            self.assertEqual(announcements, [])


if __name__ == "__main__":
    unittest.main()
