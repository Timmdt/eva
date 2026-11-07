import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.eva import EVA
from module.jarvis_module import JarvisModule
from module.startup_module import StartupModule
from module.systemtest_module import SystemTestModule


class EvaModuleTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="eva-module-tests-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for attribute, filename in (("STATE_PATH", "state.json"), ("MEMORY_PATH", "memory.json")):
            path = root / filename
            path.write_text("{}", encoding="utf-8")
            patcher = patch(f"memory.memory_engine.{attribute}", path)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Module tests neither connect to the user's database nor start voice models.
        self.enterContext(patch("core.eva.EVA._init_rag", return_value=None))
        self.enterContext(patch("core.eva.VoiceService"))

    def test_jarvis_module_can_handle_general_query(self):
        module = JarvisModule()
        self.assertTrue(module.can_handle("Wie spät ist es?"))

    def test_jarvis_module_response(self):
        module = JarvisModule()
        result = module.handle(
            "Wie spät ist es?",
            {
                "state": {"bond_level": 0.5, "current_emotion": "ruhig"},
                "module_names": ["JarvisCore"],
            },
        )
        self.assertIsInstance(result, dict)
        self.assertIn("text", result)
        self.assertIn("Es ist jetzt", result["text"])

    def test_systemtest_module(self):
        module = SystemTestModule()
        ok, msg = module.run_test()
        self.assertTrue(ok, msg)

    def test_eva_runs_all_module_tests(self):
        eva = EVA(run_module_tests=False)
        results = eva.run_module_tests()
        self.assertTrue(results)
        self.assertTrue(
            all(ok for ok, _ in results), "Mindestens ein Modultest ist fehlgeschlagen."
        )

    def test_startup_module_on_start_returns_memory(self):
        module = StartupModule()
        result = module.on_start({})
        self.assertIsInstance(result, dict)
        self.assertTrue(
            "startup_memory" in result or "fallback_text" in result,
            "StartupModule muss startup_memory oder fallback_text liefern.",
        )

    def test_eva_startup_message(self):
        eva = EVA(run_module_tests=False)
        startup_text = eva.startup()
        self.assertIsInstance(startup_text, str)
        self.assertTrue(startup_text.strip())

    def test_orphan_startup_messages_are_not_sent_to_llm(self):
        eva = EVA(run_module_tests=False)
        eva.max_history_messages = 10
        eva.state["history"] = [
            {"role": "assistant", "content": "Startup eins"},
            {"role": "user", "content": "Frage"},
            {"role": "assistant", "content": "Antwort"},
            {"role": "assistant", "content": "Startup zwei"},
        ]
        self.assertEqual(
            eva._build_message_history(),
            [
                {"role": "user", "content": "Frage"},
                {"role": "assistant", "content": "Antwort"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
