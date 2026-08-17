from __future__ import annotations

import logging

import ollama


class SearchQueryLLM:
    """
    Formuliert aus der natürlichen Benutzerfrage eine
    Suchanfrage für das Web.

    Dieses Modell beantwortet die Frage NICHT.
    """

    def __init__(
        self,
        model: str = "qwen2.5:7b-instruct-q4_K_M",
    ) -> None:
        self.model = model

    def create_query(
        self,
        user_message: str,
    ) -> str:

        if not user_message.strip():
            return ""

        system_prompt = """
Du bist der Suchanfragen-Generator von EVA.

Deine einzige Aufgabe ist es, aus der Nachricht des Benutzers
eine präzise Suchanfrage für eine Websuchmaschine zu erstellen.

Beantworte die Frage NICHT.

Keine Erklärung.
Keine Einleitung.
Keine Aufzählung.
Keine Anführungszeichen.

Gib ausschließlich die fertige Suchanfrage zurück.

Regeln:

- entferne Höflichkeitsfloskeln
- entferne "kannst du", "bitte", "sag mir" usw.
- behalte wichtige Eigennamen
- behalte Produktnamen
- behalte Modellnummern
- behalte Orte
- behalte Personen
- behalte Firmen
- behalte Jahreszahlen
- behalte aktuelle Zeitbezüge
- fasse die Frage sinnvoll für eine Suchmaschine zusammen

Beispiel:

Benutzer:
"Kannst du bitte im Internet schauen welches das neueste
ChatGPT Modell ist?"

Ausgabe:
"neuestes ChatGPT Modell OpenAI 2026"

Benutzer:
"suche mir im internet wie man einen BMW E46 umbaut"

Ausgabe:
"BMW E46 Umbau Tuning Möglichkeiten"
""".strip()

        try:

            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_message.strip(),
                    },
                ],
                options={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                },
                stream=False,
            )

            query = (
                response
                .get("message", {})
                .get("content", "")
                .strip()
            )

            query = " ".join(
                line.strip()
                for line in query.splitlines()
                if line.strip()
            )

            query = query.strip(
                "\"'`"
            )

            if not query:
                return user_message.strip()

            logging.info(
                "[SearchQueryLLM] Suchanfrage: %s",
                query,
            )

            return query

        except Exception as exc:

            logging.exception(
                "[SearchQueryLLM] Fehler: %s",
                exc,
            )

            # Fallback:
            # Die Originalnachricht kann trotzdem gesucht werden.
            return user_message.strip()