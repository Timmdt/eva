import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.env_loader import load_env_file
from core.eva import EVA
from core.intent_router import IntentDecision, IntentRouter


class EnvLoaderTest(unittest.TestCase):
    def test_loads_literal_values_without_shell_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, ".env")
            path.write_text(
                "# comment\n"
                "EVA_TEST_URL=postgresql://user:p$a@localhost/eva\n"
                "EVA_TEST_LITERAL=$(touch /tmp/must-not-run)\n"
                "EVA_TEST_QUOTED='hello world'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                loaded = load_env_file(path)
                self.assertEqual(
                    os.environ["EVA_TEST_URL"],
                    "postgresql://user:p$a@localhost/eva",
                )
                self.assertEqual(
                    os.environ["EVA_TEST_LITERAL"],
                    "$(touch /tmp/must-not-run)",
                )
                self.assertEqual(os.environ["EVA_TEST_QUOTED"], "hello world")
                self.assertEqual(
                    loaded,
                    {"EVA_TEST_URL", "EVA_TEST_LITERAL", "EVA_TEST_QUOTED"},
                )

    def test_existing_process_value_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, ".env")
            path.write_text("EVA_TEST_VALUE=from-file\n", encoding="utf-8")
            with patch.dict(os.environ, {"EVA_TEST_VALUE": "from-process"}, clear=True):
                loaded = load_env_file(path)
                self.assertEqual(os.environ["EVA_TEST_VALUE"], "from-process")
                self.assertEqual(loaded, set())

    def test_invalid_line_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, ".env")
            path.write_text("this is not an assignment\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "KEY=value"):
                load_env_file(path)


class DialogContextRegressionTest(unittest.TestCase):
    def test_smalltalk_ignores_stale_web_search_context(self):
        router = IntentRouter("unused")
        stale_context = {
            "last_tool": "WEB_SEARCH",
            "last_query": "günstige Tuningfahrzeuge Deutschland",
            "last_topic": "Tuningfahrzeuge",
        }
        stale_history = [
            {"role": "user", "content": "Welches Auto eignet sich zum Tunen?"},
            {"role": "assistant", "content": "BMW E36 und VW Polo GTI."},
        ]

        decision = router.route(
            "wie geht es dir",
            history=stale_history,
            conversation_context=stale_context,
        )

        self.assertEqual(decision.action, "NONE")
        self.assertEqual(decision.query, "")
        self.assertTrue(IntentRouter.resets_context("wie geht es dir"))

    def test_confusion_question_is_not_a_web_search_but_keeps_history(self):
        decision = IntentRouter("unused").route(
            "was",
            conversation_context={"last_tool": "WEB_SEARCH"},
        )
        self.assertEqual(decision.action, "NONE")
        self.assertFalse(IntentRouter.resets_context("was"))

    def test_explicit_weather_uses_weather_action(self):
        decision = IntentRouter("unused").route("Wie ist das Wetter in Berlin?")
        self.assertEqual(decision.action, "WEATHER")
        self.assertEqual(decision.location, "Berlin")


    def test_temperature_in_degrees_uses_weather_script(self):
        decision = IntentRouter("unused").route(
            "Kannst du schauen wieviel Grad es in Kissing aktuell ist?"
        )
        self.assertEqual(decision.action, "WEATHER")
        self.assertEqual(decision.location, "Kissing")

    def test_repeat_reuses_last_weather_location(self):
        decision = IntentRouter("unused").route(
            "nochmal",
            conversation_context={
                "last_tool": "WEATHER",
                "last_query": "wieviel Grad es in Kissing aktuell ist",
                "last_topic": "wieviel Grad es in Kissing aktuell ist",
            },
        )
        self.assertEqual(decision.action, "WEATHER")
        self.assertEqual(decision.location, "Kissing")

    def test_current_bestsellers_use_web_search(self):
        decision = IntentRouter("unused").route(
            "Was sind eigentlich die beliebtesten Bücher aktuell?"
        )
        self.assertEqual(decision.action, "WEB_SEARCH")


    def test_none_decision_clears_old_tool_query(self):
        eva = EVA.__new__(EVA)
        eva.conversation_context = {
            "last_tool": "WEB_SEARCH",
            "last_query": "alte Suche",
            "last_topic": "altes Thema",
        }

        eva._update_conversation_context(
            IntentDecision(action="NONE", query="darf nicht gespeichert werden"),
            "wie geht es dir",
        )

        self.assertIsNone(eva.conversation_context["last_tool"])
        self.assertNotIn("last_query", eva.conversation_context)
        self.assertEqual(eva.conversation_context["last_topic"], "wie geht es dir")


if __name__ == "__main__":
    unittest.main()
