"""The canonical CLI must release EVA once for every way the input loop ends."""

import io
import os
import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class MainLifecycleTest(unittest.TestCase):
    def setUp(self):
        # Do not load the user's real environment or instantiate models in tests.
        with patch("core.env_loader.load_env_file"):
            namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"))
        self.main = namespace["main"]
        self.eva = Mock()
        self.eva.name = "EVA"
        self.eva.startup.return_value = ""

    def run_cli(self, inputs):
        flags = {"EVA_HEALTH_ENABLED": "false", "EVA_PRESENCE_AUTOMATION_ENABLED": "false"}
        with (
            patch.dict(self.main.__globals__, {"EVA": Mock(return_value=self.eva)}),
            patch.dict(os.environ, flags),
            patch("builtins.input", side_effect=inputs),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.main()

    def test_exit_closes_eva_once(self):
        self.run_cli(["bye"])
        self.eva.shutdown.assert_called_once_with()

    def test_keyboard_interrupt_closes_eva_once(self):
        self.run_cli([KeyboardInterrupt()])
        self.eva.shutdown.assert_called_once_with()

    def test_end_of_input_closes_eva_once(self):
        self.run_cli([EOFError()])
        self.eva.shutdown.assert_called_once_with()

    def test_stream_error_still_closes_eva(self):
        self.eva.receive_stream.side_effect = RuntimeError("stream failed")
        with self.assertRaisesRegex(RuntimeError, "stream failed"):
            self.run_cli(["Hallo"])
        self.eva.shutdown.assert_called_once_with()

    def test_conversation_stream_remains_intact(self):
        self.eva.receive_stream.return_value = iter(["Hallo", "!"])
        self.run_cli(["", "Hallo", "exit"])
        self.eva.receive_stream.assert_called_once_with("Hallo")
        self.eva.shutdown.assert_called_once_with()
