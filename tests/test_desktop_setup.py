import os
import tempfile
import unittest
from pathlib import Path

from tools.setup_desktop_bridge import env_values, unit_text, update_env


class DesktopBridgeSetupTest(unittest.TestCase):
    def test_env_update_preserves_existing_settings_and_token_on_repeated_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "# existing\nEVA_MODEL=existing-model\nEVA_TEST_LITERAL='$(not-executed)'\nEVA_COMPANION_PORT=1\nEVA_COMPANION_PORT=2\n"
            )
            values = {
                "EVA_COMPANION_PORT": "8766",
                "EVA_COMPANION_TOKEN": "x" * 64,
                "EVA_COMPANION_HOST": "192.168.2.15",
            }
            update_env(path, values)
            first = path.read_text()
            update_env(path, values)
            self.assertEqual(path.read_text(), first)
            self.assertEqual(env_values(path)["EVA_MODEL"], "existing-model")
            self.assertEqual(env_values(path)["EVA_TEST_LITERAL"], "$(not-executed)")
            self.assertEqual(first.count("EVA_COMPANION_PORT="), 1)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_systemd_working_directory_is_an_absolute_unquoted_path(self):
        root = Path("/home/example/eva")
        unit = unit_text(root, root / ".venv/bin/python")
        self.assertIn("WorkingDirectory=/home/example/eva\n", unit)
        self.assertIn(
            'ExecStart="/home/example/eva/.venv/bin/python" -m desktop_agent.companion_server', unit
        )
        self.assertNotIn("TOKEN", unit)
        self.assertIn("WantedBy=default.target", unit)


if __name__ == "__main__":
    unittest.main()
