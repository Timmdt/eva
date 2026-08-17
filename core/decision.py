from __future__ import annotations

import json
import logging
import re

import ollama


class EVADecisionEngine:
    """
    Ein einziger Qwen-Call entscheidet:
      - answer
      - search

    Wenn search:
      zusätzlich eine saubere Suchanfrage.

    Dadurch wird Qwen nicht zweimal hintereinander geladen.
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b-instruct-q4_K_M",
    ) -> None:
        self.model = model

    def decide(
        self,
        user_message: str,
        context: str = "",
    ) -> dict[str, str]:

        system_prompt = """
Du bist der interne Entscheidungsprozessor von EVA.

Du beantwortest die Benutzerfrage NICHT.

Entscheide zwischen:

"answer"
    EVA kann direkt antworten.

"search"
    EVA benötigt externe oder aktuelle Informationen.

Verwende "search", wenn:
- der Benutzer ausdrücklich eine Internetsuche verlangt
- aktuelle Informationen benötigt werden
- aktuelle Nachrichten gefragt werden
- aktuelle Produkte, Modelle oder Releases gefragt werden
- aktuelle Preise oder Wetterdaten gefragt werden
- die Information sich nach deinem Wissen geändert haben könnte
- du die Information nicht zuverlässig kennst
- externe Recherche verlangt wird

Wenn eine Suche benötigt wird, erstelle zusätzlich eine Suchanfrage.

SEHR WICHTIG FÜR DIE SUCHANFRAGE:

Die Suchanfrage darf KEINE neuen Fakten enthalten.

Du darfst:
- Wörter entfernen
- die Formulierung vereinfachen
- Wörter neu anordnen
- Synonyme verwenden

Du darfst NICHT:
- Jahreszahlen erfinden
- Modellnamen erfinden
- Personen hinzufügen
- Orte hinzufügen
- Produkte hinzufügen
- Fakten aus deinem eigenen Wissen hinzufügen

Beispiel:

Benutzer:
"Was ist das neueste ChatGPT-Modell?"

Richtig:
"neuestes ChatGPT Modell OpenAI"

Falsch:
"neuestes ChatGPT Modell OpenAI 2023"

Benutzer:
"Kannst du im Internet nachschauen, wie man einen BMW E46 umbaut?"

Richtig:
"BMW E46 Umbau"

Falsch:
"BMW E46 2020 Tuning"

Antworte AUSSCHLIESSLICH als JSON.

Für normale Antworten:
{"action":"answer"}

Für Recherche:
{"action":"search","query":"deine Suchanfrage"}
""".strip()

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        if context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "RELEVANTER KONTEXT:\n"
                        f"{context[:3000]}"
                    ),
                }
            )

        messages.append(
            {
                "role": "user",
                "content": user_message.strip(),
            }
        )

        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": 0.0,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_ctx": 2048,
                },
                format="json",
                keep_alive=0,
                stream=False,
            )

            raw = (
                response
                .get("message", {})
                .get("content", "")
                .strip()
            )

            logging.info(
                "[DecisionEngine] Antwort: %s",
                raw,
            )

            result = self._parse_response(raw)

            action = result.get("action")

            if action not in {
                "answer",
                "search",
            }:
                raise ValueError(
                    f"Ungültige Aktion: {action}"
                )

            if action == "search":

                query = (
                    result.get("query")
                    or ""
                ).strip()

                if not query:
                    query = (
                        user_message.strip()
                    )

                result["query"] = (
                    self._sanitize_query(
                        query,
                        user_message,
                    )
                )

            logging.info(
                "[DecisionEngine] Entscheidung: %s",
                result["action"],
            )

            if result["action"] == "search":
                logging.info(
                    "[DecisionEngine] Suchquery: %s",
                    result["query"],
                )

            return result

        except Exception as exc:

            logging.exception(
                "[DecisionEngine] Fehler: %s",
                exc,
            )

            if self._explicit_search_request(
                user_message
            ):
                logging.warning(
                    "[DecisionEngine] Fallback -> search"
                )

                return {
                    "action": "search",
                    "query": user_message.strip(),
                }

            return {
                "action": "answer"
            }

    @staticmethod
    def _parse_response(
        raw: str,
    ) -> dict[str, str]:

        try:

            data = json.loads(
                raw
            )

            if isinstance(
                data,
                dict,
            ):
                return {
                    str(key): str(value)
                    for key, value in data.items()
                }

        except json.JSONDecodeError:
            pass

        action_match = re.search(
            r'"action"\s*:\s*"(answer|search)"',
            raw,
            re.IGNORECASE,
        )

        if not action_match:
            raise ValueError(
                f"Ungültige Controller-Antwort: {raw}"
            )

        result = {
            "action": (
                action_match.group(1)
                .lower()
            )
        }

        query_match = re.search(
            r'"query"\s*:\s*"(.*?)"',
            raw,
            re.IGNORECASE | re.DOTALL,
        )

        if query_match:
            result["query"] = (
                query_match.group(1)
            )

        return result

    @staticmethod
    def _sanitize_query(
        query: str,
        original: str,
    ) -> str:

        query = " ".join(
            query.split()
        ).strip(
            "\"'`"
        )

        if not query:
            return original.strip()

        # Verhindert typische Halluzinationsreste.
        forbidden_patterns = [
            r"\b20\d{2}\b",
        ]

        original_years = set(
            re.findall(
                r"\b20\d{2}\b",
                original,
            )
        )

        for pattern in forbidden_patterns:

            matches = re.findall(
                pattern,
                query,
            )

            for value in matches:
                if value not in original_years:
                    query = query.replace(
                        value,
                        "",
                    )

        query = " ".join(
            query.split()
        ).strip()

        return (
            query
            if query
            else original.strip()
        )

    @staticmethod
    def _explicit_search_request(
        text: str,
    ) -> bool:

        text = text.lower()

        phrases = [
            "suche im internet",
            "such im internet",
            "im internet suchen",
            "im internet nach",
            "suche online",
            "such online",
            "online suchen",
            "online nach",
            "recherchiere",
            "recherchier",
            "schau im internet",
            "schau online",
            "durchsuche das internet",
            "im web suchen",
        ]

        return any(
            phrase in text
            for phrase in phrases
        )