import tempfile
import unittest
from pathlib import Path

from sentry.presence import PresenceTracker
from sentry.shutdown import SafeShutdown
from sentry.wol import WakeOnLan, magic_packet


class SentryTest(unittest.TestCase):
    def test_magic_packet(self):
        packet = magic_packet("00:11:22:33:44:55")
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:12], bytes.fromhex("001122334455"))

    def test_wol_cooldown(self):
        now = [100.0]
        sent = []
        wol = WakeOnLan("00:11:22:33:44:55", "255.255.255.255", 10,
                        sender=lambda mac, broadcast: sent.append((mac, broadcast)),
                        clock=lambda: now[0])
        self.assertTrue(wol.wake())
        self.assertFalse(wol.wake())
        now[0] += 11
        self.assertTrue(wol.wake())
        self.assertEqual(len(sent), 2)

    def test_presence_timeout(self):
        now = [0.0]
        tracker = PresenceTracker(10, clock=lambda: now[0])
        self.assertTrue(tracker.update(True))
        now[0] = 9.9
        self.assertTrue(tracker.is_present())
        now[0] = 10.1
        self.assertTrue(tracker.timed_out())

    def test_shutdown_inhibit_and_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            keep = Path(directory, "keep")
            inhibit = Path(directory, "inhibit")
            called = []
            shutdown = SafeShutdown(feature_enabled=True, allow_shutdown=True,
                                    keep_awake_file=keep, inhibit_file=inhibit,
                                    boot_grace=10, uptime=lambda: 100,
                                    executor=lambda: called.append(True))
            keep.touch()
            self.assertFalse(shutdown.request().allowed)
            self.assertFalse(called)
            keep.unlink()
            dry = SafeShutdown(feature_enabled=True, allow_shutdown=False,
                               keep_awake_file=keep, inhibit_file=inhibit,
                               boot_grace=10, uptime=lambda: 100,
                               executor=lambda: called.append(True))
            decision = dry.request()
            self.assertTrue(decision.allowed)
            self.assertTrue(decision.dry_run)
            self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
