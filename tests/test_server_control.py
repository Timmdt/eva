import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from core.safe_shutdown import SafeShutdown
from interfaces.health_server import handler_factory
from interfaces.presence_state import PresenceFusion


class ServerControlTest(unittest.TestCase):
    def test_presence_endpoint_queues_automation_without_power_action(self):
        submitted = []

        class FakeAutomation:
            def submit_report(self, report):
                submitted.append(report)

        with patch.dict(os.environ, {"EVA_PRESENCE_TOKEN": ""}):
            handler = handler_factory(
                lambda: {"status": "ready"},
                automation=FakeAutomation(),
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = {
                    "sensor": "room",
                    "presence": True,
                    "identity": "Tim",
                    "confidence": 0.95,
                }
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/presence",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    self.assertEqual(response.status, 202)
                self.assertEqual(submitted, [payload])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

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
