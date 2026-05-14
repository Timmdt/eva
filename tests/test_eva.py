import unittest

from core.eva import EVA
from module.jarvis_module import JarvisModule
from module.test_module import TestModule


class EvaModuleTest(unittest.TestCase):
    def test_jarvis_module_can_handle_general_query(self):
        module = JarvisModule()
        self.assertTrue(module.can_handle("Wie spät ist es?"))

    def test_jarvis_module_response(self):
        module = JarvisModule()
        result = module.handle("Wie spät ist es?", {"state": {"bond_level": 0.5, "current_emotion": "ruhig"}, "module_names": ["JarvisCore"]})
        self.assertIsInstance(result, dict)
        self.assertIn("text", result)
        self.assertIn("Es ist jetzt", result["text"])

    def test_module_test_module(self):
        module = TestModule()
        ok, msg = module.run_test()
        self.assertTrue(ok, msg)

    def test_eva_runs_all_module_tests(self):
        eva = EVA(run_module_tests=False)
        results = eva.run_module_tests()
        self.assertTrue(results)
        self.assertTrue(all(ok for ok, _ in results), "Mindestens ein Modultest ist fehlgeschlagen.")


if __name__ == "__main__":
    unittest.main()
