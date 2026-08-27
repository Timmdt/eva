import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any

try:
    import ollama
except ImportError:
    ollama = None


logger = logging.getLogger(__name__)


ALLOWED_ACTIONS = {
    "NONE",
    "WEB_SEARCH",
    "WIKIPEDIA",
    "WEATHER",
    "URL",
    "MEMORY",
    "RAG",
    "WEB_SEARCH_MEMORY",
    "WEB_SEARCH_RAG",
}


ROUTER_PROMPT = r"""
Du bist EVAs Intent-Router. Du beantwortest die Benutzerfrage NICHT.
Du entscheidest nur, welche Datenquellen EVA vor der eigentlichen Antwort braucht.

AKTIONEN
NONE
- Allgemeines Wissen, Rechnen, Schreiben, Programmieren, Unterhaltung oder Meinung.
- Keine aktuellen externen Daten und kein persönliches Langzeitgedächtnis nötig.

WEB_SEARCH
- Aktuelle, externe, überprüfbare oder sehr spezielle Informationen sind nötig oder sinnvoll.
- Der Benutzer möchte recherchieren, vergleichen, Preise, Verfügbarkeit, aktuelle Technik,
  Nachrichten, Gesetze, Versionen, Produkte oder andere Informationen aus dem Web.
- Auch Folgefragen zu einer laufenden Web-Recherche können WEB_SEARCH benötigen.

WIKIPEDIA
- Der Benutzer möchte ausdrücklich Wikipedia oder einen enzyklopädischen Überblick.

WEATHER
- Aktuelles Wetter oder Vorhersage für einen Ort.

URL
- Der Benutzer möchte den Inhalt einer konkreten URL untersuchen.

MEMORY
- Die Antwort hängt von EVAs Langzeitgedächtnis ab: frühere Entscheidungen,
  persönliche Präferenzen, bekannte Projekte, Fortschritt oder vergangene Gespräche.

RAG
- Die Antwort soll aus EVAs lokaler Dokumentensammlung/Knowledge Base belegt werden.
- Nutze RAG bei Fragen nach ingestierten Dokumenten, Handbüchern oder lokalen Wissensquellen.

WEB_SEARCH_MEMORY
- Sowohl aktuelle Webdaten als auch EVAs Langzeitgedächtnis werden benötigt.

WEB_SEARCH_RAG
- Sowohl aktuelle Webdaten als auch lokale Dokumente werden benötigt.

REGELN
1. Interpretiere die aktuelle Nachricht IM KONTEXT der vorherigen Unterhaltung.
2. Folgefragen wie "und was davon?", "welches davon?" oder "wie sieht es damit aus?"
   beziehen sich auf das vorherige Thema.
3. Nutze WEB_SEARCH nicht nur wegen einzelner Wörter. Entscheide semantisch.
4. Nutze WEB_SEARCH auch ohne ausdrückliche Aufforderung, wenn Aktualität entscheidend ist.
5. Nutze NONE, wenn das Modell die Frage stabil aus allgemeinem Wissen beantworten kann.
6. Nutze MEMORY nur, wenn persönliche oder gespeicherte Informationen wirklich gebraucht werden.
7. Erfinde keine Dossiernamen. Wenn ein passendes Dossier aus MEMORY_INDEX existiert,
   gib dessen Namen exakt in dossier zurück.
8. query muss eine kurze, eigenständige Suchanfrage sein. Löse Pronomen und Folgebezüge auf.
9. confidence liegt zwischen 0.0 und 1.0.
10. Antworte ausschließlich mit einem JSON-Objekt. Kein Markdown, keine Erklärung außen herum.

SCHEMA
{
  "action": "NONE|WEB_SEARCH|WIKIPEDIA|WEATHER|URL|MEMORY|RAG|WEB_SEARCH_MEMORY|WEB_SEARCH_RAG",
  "query": "eigenständige Such-/Memory-Anfrage oder leer",
  "dossier": "exakter Dossiername oder leer",
  "location": "Ort oder leer",
  "url": "URL oder leer",
  "confidence": 0.0,
  "reason": "sehr kurze interne Begründung"
}

BEISPIELE
Vorher: Benutzer fragte nach aktuellen Grafikkartenpreisen.
Aktuell: "Und welche davon ist am günstigsten?"
=> WEB_SEARCH, query enthält Grafikkarten + Preisvergleich.

Vorher: Gespräch über das gespeicherte Projekt Lumora.
Aktuell: "Wie weit waren wir da nochmal?"
=> MEMORY und dossier "Lumora", sofern es im MEMORY_INDEX steht.

Aktuell: "Erklär mir Rekursion in Python."
=> NONE.
""".strip()


@dataclass
class IntentDecision:
    action: str = "NONE"
    query: str = ""
    dossier: str = ""
    location: str = ""
    url: str = ""
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntentRouter:
    """Semantischer Tool-Router für EVA."""

    def __init__(
        self,
        model: str,
        *,
        history_messages: int = 6,
        max_dossiers: int = 20,
        keep_alive: str = "30m",
    ) -> None:
        self.model = model
        self.history_messages = history_messages
        self.max_dossiers = max_dossiers
        self.keep_alive = keep_alive

    def route(
        self,
        user_message: str,
        *,
        history: list[dict[str, str]] | None = None,
        conversation_context: dict[str, Any] | None = None,
        memory_index: list[dict[str, Any]] | None = None,
    ) -> IntentDecision:
        fast = self._fast_route(user_message)
        if fast is not None:
            return fast
        if ollama is None:
            logger.warning("Ollama nicht verfügbar; IntentRouter fällt auf NONE zurück.")
            return IntentDecision(
                action="NONE",
                confidence=0.0,
                reason="Ollama nicht verfügbar",
            )

        payload = self._build_payload(
            user_message,
            history=history or [],
            conversation_context=conversation_context or {},
            memory_index=memory_index or [],
        )

        messages = [
            {"role": "system", "content": ROUTER_PROMPT},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False),
            },
        ]

        try:
            # Neuere Ollama-Versionen können JSON-Ausgabe erzwingen.
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=messages,
                    format="json",
                    options={
                        "temperature": 0.0,
                        "top_p": 0.75,
                        "num_predict": 220,
                    },
                    stream=False,
                    keep_alive=self.keep_alive,
                )
            except TypeError:
                # Kompatibilität mit älteren Python-Clients.
                response = ollama.chat(
                    model=self.model,
                    messages=messages,
                    options={
                        "temperature": 0.0,
                        "top_p": 0.75,
                        "num_predict": 220,
                    },
                    stream=False,
                    keep_alive=self.keep_alive,
                )

            raw = str(response["message"]["content"]).strip()
            decision = self._parse(raw)

            logger.debug(
                "[IntentRouter] action=%s confidence=%.2f query=%r dossier=%r",
                decision.action,
                decision.confidence,
                decision.query,
                decision.dossier,
            )
            return decision

        except Exception:
            logger.exception("IntentRouter fehlgeschlagen; verwende NONE.")
            return IntentDecision(
                action="NONE",
                confidence=0.0,
                reason="Router-Fehler",
            )

    @staticmethod
    def _fast_route(user_message: str) -> IntentDecision | None:
        """Only unambiguous intents bypass the semantic model."""
        clean = " ".join(user_message.strip().split())
        lowered = clean.casefold()
        url = re.search(r"https?://[^\s]+", clean)
        if url:
            return IntentDecision(action="URL", url=url.group(0), query=clean,
                                  confidence=1.0, reason="explizite URL")
        if re.search(r"\b(suche|recherchiere|schau|prüfe)\b.{0,30}\b(web|internet|online)\b",
                     lowered):
            return IntentDecision(action="WEB_SEARCH",
                                  query=IntentRouter._explicit_web_query(clean), confidence=0.99,
                                  reason="explizite Websuche")
        if re.search(
            r"^(?:(?:kannst|könntest|würdest) du\s+)?(?:bitte\s+)?"
            r"(?:such|suche|suchen|recherchiere|recherchier)\b",
            lowered,
        ):
            return IntentDecision(action="WEB_SEARCH",
                                  query=IntentRouter._explicit_web_query(clean), confidence=0.99,
                                  reason="expliziter Suchauftrag")
        if re.search(r"\b(lokale[sn]? dokument|ingestiert|knowledge base|rag[- ](?:daten|wissen)|handbuch)\w*\b",
                     lowered):
            return IntentDecision(action="RAG", query=clean, confidence=0.98,
                                  reason="explizite lokale Dokumentquelle")
        return None

    @staticmethod
    def _explicit_web_query(message: str) -> str:
        query = message.strip()
        query = re.sub(
            r"^(?:(?:kannst|könntest|würdest) du\s+)?(?:bitte\s+)?"
            r"(?:such|suche|suchen|recherchiere|recherchier)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(r"^(?:im|in dem)\s+(?:internet|web|netz)\s+(?:nach\s+)?",
                       "", query, flags=re.IGNORECASE)
        query = query.strip(" ?!.,:") or message.strip()
        lowered = query.casefold()
        if re.search(r"\bauto\w*\b", lowered) and re.search(r"\btun(?:en|ing)\w*\b", lowered):
            query += (
                " Gebrauchtwagen Modelle Vergleich Tuningpotenzial "
                "Teileverfügbarkeit Unterhaltskosten Deutschland"
            )
        return query[:499]

    def _build_payload(
        self,
        user_message: str,
        *,
        history: list[dict[str, str]],
        conversation_context: dict[str, Any],
        memory_index: list[dict[str, Any]],
    ) -> dict[str, Any]:
        clean_history: list[dict[str, str]] = []

        for item in history[-self.history_messages :]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                clean_history.append(
                    {
                        "role": role,
                        # Router braucht nur Kontext, keine riesigen Antworten.
                        "content": content[:1200],
                    }
                )

        dossiers: list[dict[str, Any]] = []
        for item in memory_index[: self.max_dossiers]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            dossiers.append(
                {
                    "name": name,
                    "keywords": list(item.get("keywords", []))[:8],
                }
            )

        return {
            "conversation_context": {
                "last_tool": conversation_context.get("last_tool"),
                "last_query": conversation_context.get("last_query"),
                "last_topic": conversation_context.get("last_topic"),
            },
            "memory_index": dossiers,
            "recent_history": clean_history,
            "current_message": user_message,
        }

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def _parse(self, raw: str) -> IntentDecision:
        data = self._extract_json(raw)
        if not data:
            return IntentDecision(
                action="NONE",
                confidence=0.0,
                reason="Ungültige Router-Ausgabe",
            )

        action = str(data.get("action", "NONE")).upper().strip()
        if action not in ALLOWED_ACTIONS:
            action = "NONE"

        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        confidence = max(0.0, min(1.0, confidence))

        return IntentDecision(
            action=action,
            query=str(data.get("query", "") or "").strip(),
            dossier=str(data.get("dossier", "") or "").strip(),
            location=str(data.get("location", "") or "").strip(),
            url=str(data.get("url", "") or "").strip(),
            confidence=confidence,
            reason=str(data.get("reason", "") or "").strip()[:240],
        )
