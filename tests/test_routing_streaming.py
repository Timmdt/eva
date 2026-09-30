import unittest
from unittest.mock import Mock

from core.eva import EVA
from core.intent_router import IntentDecision, IntentRouter
from module.web_search_module import WebSearchModule


class RoutingStreamingTest(unittest.TestCase):
    def test_intent_router_parses_rag(self):
        router = IntentRouter("unused")
        decision = router._parse('{"action":"RAG","query":"Handbuch","confidence":0.9}')
        self.assertEqual(decision.action, "RAG")
        self.assertEqual(decision.query, "Handbuch")

    def test_explicit_local_document_uses_fast_rag_route(self):
        router = IntentRouter("unused")
        decision = router.route("Fasse das lokale Handbuch zusammen")
        self.assertEqual(decision.action, "RAG")
        self.assertGreater(decision.confidence, 0.9)

    def test_general_knowledge_question_skips_model_router(self):
        router = IntentRouter("unused")
        decision = router.route("Warum ändern Blätter im Herbst ihre Farbe?")
        self.assertEqual(decision.action, "NONE")
        self.assertGreater(decision.confidence, 0.9)

    def test_encyclopedic_overview_uses_wikipedia_with_clean_subject(self):
        router = IntentRouter("unused")
        decision = router.route("kannst du mir was über dem BMW E46 erzählen")
        self.assertEqual(decision.action, "WIKIPEDIA")
        self.assertEqual(decision.query, "BMW E46")

    def test_story_requests_never_trigger_web_or_wikipedia(self):
        router = IntentRouter("unused")
        requests = (
            "Kannst du mir eine Geschichte von den Brüdern Grimm erzählen?",
            "Kannst du mir eine Gute-Nacht-Geschichte erzählen?",
            "Erzähl mir bitte ein Märchen.",
            "Kannst du mir nochmal eine erzählen, am besten eine von Gebrüder Grim?",
        )
        for request in requests:
            with self.subTest(request=request):
                decision = router.route(request)
                self.assertEqual(decision.action, "NONE")
                self.assertEqual(decision.confidence, 1.0)

    def test_story_mode_discards_polluted_answer_history(self):
        eva = EVA.__new__(EVA)
        eva.cfg = {"profile_memory_isolation": False}
        eva._get_current_time = Mock(return_value=None)
        eva._build_runtime_context = Mock(return_value="runtime")
        eva._build_relevant_memory_hint = Mock(return_value=None)
        eva._build_message_history = Mock(return_value=[
            {"role": "assistant", "content": "Schlechte alte Antwort mit Quellen"},
        ])

        messages = eva._build_messages(
            "Kannst du mir eine Geschichte von den Brüdern Grimm erzählen?"
        )
        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("ERZÄHLMODUS", combined)
        self.assertNotIn("Schlechte alte Antwort", combined)
        eva._build_message_history.assert_not_called()

    def test_explicit_tuning_search_preserves_meaning(self):
        router = IntentRouter("unused")
        decision = router.route(
            "kannst du suchen welches auto am besten sich fürs tunen eignet und relativ günstig ist"
        )
        self.assertEqual(decision.action, "WEB_SEARCH")
        self.assertIn("tunen", decision.query.casefold())
        self.assertNotIn("zumuten", decision.query.casefold())
        self.assertIn("Teileverfügbarkeit", decision.query)

    def test_web_search_result_is_injected(self):
        eva = EVA.__new__(EVA)
        eva._run_web_action = Mock(return_value="LIVE RESULT")
        eva._memory_context_from_decision = Mock(return_value=None)
        result = eva._execute_intent(
            IntentDecision(action="WEB_SEARCH", query="aktuell"), "frage")
        self.assertEqual(result, ("LIVE RESULT", None))

    def test_quick_wellbeing_reply_avoids_formal_help_phrase(self):
        reply = EVA._quick_conversation_response("hi wie geht es dir")
        self.assertEqual(reply, "Hi, mir geht es gut, danke. Und wie geht es dir?")
        self.assertNotIn("Ihnen", reply)

    def test_wikipedia_summary_bypasses_language_model(self):
        web_data = (
            "[System-Meldung: Live-Web-Daten geladen]\n\nWIKIPEDIA\n"
            "Titel: BMW E46\nBeschreibung: Pkw-Baureihe\n"
            "Zusammenfassung: Der BMW E46 ist die vierte Generation der BMW-3er-Reihe. "
            "Er kam 1998 auf den Markt.\n"
            "Quelle: https://de.wikipedia.org/wiki/BMW_E46"
        )
        eva = EVA.__new__(EVA)
        eva._chat_stream = Mock(side_effect=AssertionError("LLM darf nicht laufen"))
        output = "".join(eva.generate_response_stream("Erzähl mir etwas", web_data=web_data))
        self.assertIn("vierte Generation", output)
        self.assertIn("https://de.wikipedia.org/wiki/BMW_E46", output)
        eva._chat_stream.assert_not_called()

    def test_weather_result_bypasses_language_model(self):
        web_data = (
            "[System-Meldung: Live-Web-Daten geladen]\n\nWETTER\n"
            "Ort: Kissing\nTemperatur: 17 °C\nGefühlt: 16 °C\n"
            "Wetter: Leicht bewölkt\nLuftfeuchtigkeit: 62 %\n"
            "Wind: 9 km/h\nQuelle: wttr.in"
        )
        eva = EVA.__new__(EVA)
        eva._chat_stream = Mock(side_effect=AssertionError("LLM darf nicht laufen"))
        output = "".join(eva.generate_response_stream("Wie warm ist es?", web_data=web_data))
        self.assertIn("Kissing", output)
        self.assertIn("17 °C", output)
        self.assertIn("62 %", output)
        self.assertIn("wttr.in", output)
        eva._chat_stream.assert_not_called()

    def test_weather_failure_is_explicit_and_bypasses_language_model(self):
        web_data = (
            "WETTER_FEHLER\nOrt: Kissing\n"
            "Fehler: Der Wetterdienst ist nicht erreichbar."
        )
        eva = EVA.__new__(EVA)
        eva._chat_stream = Mock(side_effect=AssertionError("LLM darf nicht laufen"))
        output = "".join(eva.generate_response_stream("nochmal", web_data=web_data))
        self.assertIn("Wetterskript", output)
        self.assertIn("nicht erreichbar", output)
        self.assertNotIn("penguin", output.casefold())
        eva._chat_stream.assert_not_called()


    def test_general_web_prompt_is_spoken_friendly(self):
        eva = EVA(run_module_tests=False)
        messages = eva._build_web_answer_messages(
            "Erzähl mir etwas über den BMW E46", "WIKIPEDIA\nQuelle: test"
        )
        prompt = messages[0]["content"]
        self.assertIn("grammatisch vollständige Sätze", prompt)
        self.assertNotIn("Alternativen je nach Tuningziel", prompt)

    def test_web_prompt_requires_direct_comparison(self):
        eva = EVA(run_module_tests=False)
        messages = eva._build_messages("Welches Auto?", web_data="WEB RESULTS")
        web_prompt = next(item["content"] for item in messages
                          if item["role"] == "system" and "LIVE-WEB-DATEN" in item["content"])
        self.assertIn("konkrete Kandidaten", web_prompt)
        self.assertIn("allgemeine Such- oder Kauftipps", web_prompt)

    def test_search_results_enrich_best_article(self):
        module = WebSearchModule()
        module.fetch_url = Mock(return_value={"url": "https://example.test/article",
                                              "text": "Konkrete Modelle " * 30})
        results = [
            {"title": "Gebrauchtwagenangebote", "url": "https://market.test/list", "snippet": "x"},
            {"title": "Welches Auto eignet sich am besten?",
             "url": "https://example.test/article", "snippet": "y"},
        ]
        text = module._format_search_results("Tuning Autos", results)
        self.assertIn("SEITENEXZERPT", text)
        self.assertIn("Konkrete Modelle", text)
        module.fetch_url.assert_called_once()

    def test_page_excerpt_is_focused_around_search_snippet(self):
        navigation = "Navigation " * 500
        relevant = "Fazit: Am besten geeignet. Günstige Basisfahrzeuge: BMW E36, VW Polo GTI."
        focused = WebSearchModule._focus_excerpt(
            navigation + relevant,
            "Fazit: Am besten geeignet.",
            500,
        )
        self.assertIn("BMW E36", focused)
        self.assertLess(len(focused), 501)

    def test_relevant_excerpt_prioritizes_user_constraint(self):
        excerpt = (
            "Turbo-Modelle: VW Golf GTI, Audi S3. "
            "Weitere allgemeine Erläuterungen. " * 12
            + "Günstige Basisfahrzeuge mit erschwinglichem Einstieg: BMW E36, VW Polo GTI."
        )
        relevant = WebSearchModule._relevant_excerpt(
            "welches Auto ist zum Tunen relativ günstig",
            excerpt,
            500,
        )
        self.assertIn("Günstige Basisfahrzeuge", relevant)
        self.assertIn("BMW E36", relevant)

    def test_relevant_excerpt_excludes_previous_category(self):
        excerpt = (
            "Sportwagen: Honda Civic Type R. "
            "Günstige Basisfahrzeuge: BMW E36, VW Polo GTI."
        )
        relevant = WebSearchModule._relevant_excerpt(
            "relativ günstig tunen",
            excerpt,
        )
        self.assertNotIn("Honda", relevant)
        self.assertIn("BMW E36", relevant)

    def test_relevant_excerpt_stops_before_next_section(self):
        relevant = WebSearchModule._relevant_excerpt(
            "relativ günstig tunen",
            "Günstige Basisfahrzeuge: BMW E36, VW Polo GTI. Fazit: Turbos sind stark.",
        )
        self.assertIn("VW Polo GTI", relevant)
        self.assertNotIn("Turbos", relevant)

    def test_relevant_excerpt_keeps_offset_after_sharp_s(self):
        relevant = WebSearchModule._relevant_excerpt(
            "relativ günstig tunen",
            "Großes Potenzial. Günstige Basisfahrzeuge: BMW E36, VW Polo GTI.",
        )
        self.assertTrue(relevant.startswith("Günstige Basisfahrzeuge"))

    def test_example_evidence_keeps_categories_separate(self):
        excerpt = (
            "Einleitung. Turboautos bieten Softwarepotenzial. "
            "Beispiele: VW Golf GTI, Audi S3. "
            "Große Communities bieten viele Teile. "
            "Beispiele: VW Golf, BMW 3er. "
            "Günstige Basisfahrzeuge eignen sich für Einsteiger. "
            "Beispiele: BMW E36, VW Polo GTI. Fazit: Auswahl nach Ziel."
        )
        primary = "Günstige Basisfahrzeuge eignen sich für Einsteiger. Beispiele: BMW E36, VW Polo GTI."
        evidence = WebSearchModule._example_evidence(excerpt, exclude_text=primary)
        self.assertIn("Turboautos", evidence)
        self.assertIn("Große Communities", evidence)
        self.assertNotIn("BMW E36", evidence)

    def test_stream_is_collected_before_history_write(self):
        eva = EVA(run_module_tests=False)
        eva.module_manager.route = Mock(return_value=None)
        eva._route_intent = Mock(return_value=IntentDecision(action="NONE"))
        eva._execute_intent = Mock(return_value=(None, None))
        eva.generate_response_stream = Mock(return_value=iter(["Hallo", " Welt"]))
        eva._append_history = Mock()
        output = "".join(eva.receive_stream("Test"))
        self.assertEqual(output, "Hallo Welt")
        eva._append_history.assert_called_once_with("Test", "Hallo Welt")

    def test_voice_receives_stream_while_history_keeps_full_response(self):
        eva = EVA(run_module_tests=False)
        eva.module_manager.route = Mock(return_value=None)
        eva._route_intent = Mock(return_value=IntentDecision(action="NONE"))
        eva._execute_intent = Mock(return_value=(None, None))
        eva.generate_response_stream = Mock(return_value=iter(["Hallo. ", "Alles läuft."]))
        eva._append_history = Mock()
        eva.voice = Mock()
        eva.voice.start_response.return_value = 7
        eva.voice.metrics.snapshot.return_value = {}

        output = "".join(eva.receive_stream("Test"))

        self.assertEqual(output, "Hallo. Alles läuft.")
        self.assertEqual(
            [call.args[0] for call in eva.voice.feed_text.call_args_list],
            ["Hallo. ", "Alles läuft."],
        )
        eva.voice.finish_response.assert_called_once_with()
        eva._append_history.assert_called_once_with("Test", "Hallo. Alles läuft.")

    def test_internal_tags_are_removed_across_stream_chunks(self):
        chunks = iter(["Antwort ", "[LOAD_", "DOSSIER: Intern]", " sichtbar"])
        self.assertEqual("".join(EVA._visible_stream(chunks)), "Antwort  sichtbar")

    def test_web_stream_appends_missing_exact_source(self):
        output = "".join(EVA._web_stream_with_sources(
            iter(["Kurzfazit", "\nDatenlage"]),
            "Quelle: https://example.test/article",
        ))
        self.assertIn("Kurzfazit", output)
        self.assertIn("Quellen:\n- https://example.test/article", output)

    def test_web_stream_does_not_duplicate_exact_source(self):
        answer = "Quellen:\n- https://example.test/article"
        output = "".join(EVA._web_stream_with_sources(
            iter([answer]),
            "Quelle: https://example.test/article",
        ))
        self.assertEqual(output, answer)


if __name__ == "__main__":
    unittest.main()
