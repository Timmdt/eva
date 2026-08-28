import tempfile
import unittest
from pathlib import Path

from core.safe_shutdown import SafeShutdown
from interfaces.presence_state import PresenceFusion


class ServerControlTest(unittest.TestCase):
    def test_shutdown_is_inhibited_and_dry_run_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            keep = Path(directory, "keep")
            inhibit = Path(directory, "inhibit")
            calls = []
            shutdown = SafeShutdown(
                feature_enabled=True, allow_shutdown=False,
                keep_awake_file=keep, inhibit_file=inhibit,
                boot_grace=10, uptime=lambda: 100,
                executor=lambda: calls.append(True),
            )
            keep.touch()
            self.assertFalse(shutdown.request().allowed)
            keep.unlink()
            decision = shutdown.request()
            self.assertTrue(decision.allowed)
            self.assertTrue(decision.dry_run)
            self.assertFalse(calls)

    def test_stale_desk_presence_closes_private_context(self):
        now = [0.0]
        fusion = PresenceFusion(ttl_seconds=10, clock=lambda: now[0])
        state = fusion.update({"sensor": "desk", "presence": True, "identity": "Tim"})
        self.assertTrue(state.personal_context_allowed)
        now[0] = 10.1
        self.assertFalse(fusion.current().personal_context_allowed)


if __name__ == "__main__":
    unittest.main()
