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


CONVERSATIONAL_PATTERNS = (
    r"(?:hallo|hi|hey|moin|servus|guten (?:morgen|tag|abend))",
    r"(?:wie geht(?: es|s)? dir|wie fühlst du dich|alles gut bei dir)",
    r"(?:danke|dankeschön|vielen dank|bitte|gern geschehen)",
    r"(?:was|hä|häh|bitte was|wie bitte|was meinst du)",
    r"(?:okay|ok|alles klar|verstehe|cool)",
    r"(?:wer bist du|was bist du|was kannst du)",
)

CONTEXT_RESET_PATTERNS = (
    CONVERSATIONAL_PATTERNS[0],
    CONVERSATIONAL_PATTERNS[1],
    CONVERSATIONAL_PATTERNS[2],
    CONVERSATIONAL_PATTERNS[4],
    CONVERSATIONAL_PATTERNS[5],
)

STORY_PATTERNS = (
    r"\b(?:märchen|maerchen|gutenachtgeschichte|gute[- ]nacht[- ]geschichte)\b",
    r"\b(?:brüder|gebrüder|brueder|gebrueder)\s+grimm?\b",
    r"\berzähl\w*\b.{0,80}\b(?:eine|eine kurze|eine kleine)\s+geschichte\b",
    r"\b(?:eine|eine kurze|eine kleine)\s+geschichte\b.{0,80}\berzähl\w*\b",
)

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
1. Die aktuelle Nachricht hat immer Vorrang. Ist sie eigenständig oder wechselt
   erkennbar das Thema, ignoriere frühere Suchanfragen vollständig.
2. Folgefragen wie "und was davon?", "welches davon?" oder "wie sieht es damit aus?"
   beziehen sich auf das vorherige Thema.
3. Smalltalk, Begrüßungen, Rückfragen wie "was?" und Fragen an EVA selbst sind
   immer NONE. Verwandle sie niemals in eine frühere Websuche.
4. Nutze WEB_SEARCH nicht nur wegen einzelner Wörter. Entscheide semantisch.
5. Nutze WEB_SEARCH auch ohne ausdrückliche Aufforderung, wenn Aktualität entscheidend ist.
6. Nutze NONE, wenn das Modell die Frage stabil aus allgemeinem Wissen beantworten kann.
7. Nutze MEMORY nur, wenn persönliche oder gespeicherte Informationen wirklich gebraucht werden.
8. Erfinde keine Dossiernamen. Wenn ein passendes Dossier aus MEMORY_INDEX existiert,
   gib dessen Namen exakt in dossier zurück.
9. query muss eine kurze, eigenständige Suchanfrage sein. Löse Pronomen und Folgebezüge auf.
10. confidence liegt zwischen 0.0 und 1.0.
11. Antworte ausschließlich mit einem JSON-Objekt. Kein Markdown, keine Erklärung außen herum.

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
        num_ctx: int = 2048,
    ) -> None:
        self.model = model
        self.history_messages = history_messages
        self.max_dossiers = max_dossiers
        self.keep_alive = keep_alive
        self.num_ctx = max(512, int(num_ctx))

    def route(
        self,
        user_message: str,
        *,
        history: list[dict[str, str]] | None = None,
        conversation_context: dict[str, Any] | None = None,
        memory_index: list[dict[str, Any]] | None = None,
    ) -> IntentDecision:
        """Ordnet einer Nachricht die passende Datenquelle oder NONE zu."""
        conversation_context = conversation_context or {}
        fast = self._fast_route(user_message, conversation_context)
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
            conversation_context=conversation_context,
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
                        "num_ctx": self.num_ctx,
                    },
                    think=False,
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
                        "num_ctx": self.num_ctx,
                    },
                    think=False,
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
    def is_conversational(user_message: str) -> bool:
        """Erkennt kurze Unterhaltung, die keine externe Quelle benötigt."""
        lowered = " ".join(user_message.strip().split()).casefold()
        return any(
            re.fullmatch(pattern + r"[?!.]*", lowered) for pattern in CONVERSATIONAL_PATTERNS
        )

    @staticmethod
    def resets_context(user_message: str) -> bool:
        """Erkennt Nachrichten, die ein neues Gesprächsthema beginnen."""
        lowered = " ".join(user_message.strip().split()).casefold()
        return any(re.fullmatch(pattern + r"[?!.]*", lowered) for pattern in CONTEXT_RESET_PATTERNS)

    @staticmethod
    def is_story_request(user_message: str) -> bool:
        """Erkennt Erzählwünsche, die keine Webrecherche benötigen."""
        lowered = " ".join(user_message.strip().split()).casefold()
        return any(re.search(pattern, lowered) for pattern in STORY_PATTERNS)

    @staticmethod
    def _fast_route(
        user_message: str,
        conversation_context: dict[str, Any] | None = None,
    ) -> IntentDecision | None:
        """Leitet nur eindeutige Absichten ohne semantisches Modell weiter."""
        clean = " ".join(user_message.strip().split())
        lowered = clean.casefold()
        conversation_context = conversation_context or {}
        if IntentRouter.is_conversational(clean):
            return IntentDecision(
                action="NONE",
                confidence=1.0,
                reason="klare Unterhaltung ohne externe Daten",
            )
        if IntentRouter.is_story_request(clean):
            return IntentDecision(
                action="NONE",
                confidence=1.0,
                reason="kreativer Erzählwunsch ohne externe Daten",
            )
        if re.fullmatch(r"(?:nochmal|noch einmal|wiederhol(?:e das)?)[?!.]*", lowered):
            if conversation_context.get("last_tool") == "WEATHER":
                previous = str(
                    conversation_context.get("last_query")
                    or conversation_context.get("last_topic")
                    or ""
                )
                return IntentDecision(
                    action="WEATHER",
                    query=previous or clean,
                    location=IntentRouter._weather_location(previous) or "Kissing",
                    confidence=1.0,
                    reason="Wiederholung der letzten Wetterabfrage",
                )
        if re.search(
            r"\b(?:wetter|wettervorhersage|temperatur|regnet|regen|schnee)\b"
            r"|\bwie (?:warm|kalt)\b"
            r"|\b(?:wie\s+viel|wieviel)\s+grad\b",
            lowered,
        ):
            location = IntentRouter._weather_location(clean)
            return IntentDecision(
                action="WEATHER",
                query=clean,
                location=location,
                confidence=0.99,
                reason="explizite Wetterfrage",
            )
        url = re.search(r"https?://[^\s]+", clean)
        if url:
            return IntentDecision(
                action="URL", url=url.group(0), query=clean, confidence=1.0, reason="explizite URL"
            )
        overview_query = IntentRouter._encyclopedic_query(clean)
        if overview_query:
            return IntentDecision(
                action="WIKIPEDIA",
                query=overview_query,
                confidence=0.98,
                reason="enzyklopädischer Überblick über ein benanntes Thema",
            )
        if re.search(
            r"\b(?:aktuell|derzeit|momentan|neueste\w*|beliebteste\w*|bestseller)\b",
            lowered,
        ):
            return IntentDecision(
                action="WEB_SEARCH",
                query=clean,
                confidence=0.99,
                reason="aktuelle oder wechselnde Information",
            )
        if re.search(
            r"\b(suche|recherchiere|schau|prüfe)\b.{0,30}\b(web|internet|online)\b", lowered
        ):
            return IntentDecision(
                action="WEB_SEARCH",
                query=IntentRouter._explicit_web_query(clean),
                confidence=0.99,
                reason="explizite Websuche",
            )
        if re.search(
            r"^(?:(?:kannst|könntest|würdest) du\s+)?(?:bitte\s+)?"
            r"(?:such|suche|suchen|recherchiere|recherchier)\b",
            lowered,
        ):
            return IntentDecision(
                action="WEB_SEARCH",
                query=IntentRouter._explicit_web_query(clean),
                confidence=0.99,
                reason="expliziter Suchauftrag",
            )
        if re.search(
            r"\b(lokale[sn]? dokument|ingestiert|knowledge base|rag[- ](?:daten|wissen)|handbuch)\w*\b",
            lowered,
        ):
            return IntentDecision(
                action="RAG", query=clean, confidence=0.98, reason="explizite lokale Dokumentquelle"
            )
        if re.search(
            r"^(?:erklär\w*|warum\b|wie funktioniert\b|was (?:ist|sind)\b|"
            r"was bedeutet\b|welchen unterschied\b|unterschied zwischen\b)",
            lowered,
        ):
            return IntentDecision(
                action="NONE",
                confidence=0.98,
                reason="allgemeine Wissensfrage ohne externe Daten",
            )
        return None

    @staticmethod
    def _weather_location(message: str) -> str:
        """Extrahiert nur den Ort, nicht Wörter wie 'aktuell ist'."""
        clean = " ".join(message.strip().split())
        match = re.search(
            r"\bin\s+(.+?)(?=\s+(?:aktuell|gerade|heute|jetzt|zurzeit|momentan)\b|[?!.]|$)",
            clean,
            flags=re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"\b(?:in|für)\s+([^?!.]+)",
                clean,
                flags=re.IGNORECASE,
            )
        if not match:
            return ""
        location = match.group(1).strip(" ?!.,:")
        location = re.sub(
            r"\s+(?:aktuell|gerade|heute|jetzt|zurzeit|momentan)(?:\s+ist)?$",
            "",
            location,
            flags=re.IGNORECASE,
        )
        location = location[:1].upper() + location[1:]
        return location[:120]

    @staticmethod
    def _encyclopedic_query(message: str) -> str:
        """Extrahiert das Thema einer allgemeinen Wissensfrage."""
        patterns = (
            r"\b(?:etwas|was|infos?|informationen?|fakten)\s+(?:über|zu)\s+"
            r"(?:(?:den|dem|der|die|das)\s+)?(.+?)(?:\s+erzählen)?[?!.]*$",
            r"\b(?:erzähl|erzähle)\w*\s+(?:mir\s+)?(?:etwas|was)?\s*"
            r"(?:über|zu)\s+(?:(?:den|dem|der|die|das)\s+)?(.+?)[?!.]*$",
        )
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip(" ?!.,:")[:499]
        return ""

    @staticmethod
    def _explicit_web_query(message: str) -> str:
        """Entfernt Befehlswörter aus einem ausdrücklichen Suchauftrag."""
        query = message.strip()
        query = re.sub(
            r"^(?:(?:kannst|könntest|würdest) du\s+)?(?:bitte\s+)?"
            r"(?:such|suche|suchen|recherchiere|recherchier)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        )
        query = re.sub(
            r"^(?:im|in dem)\s+(?:internet|web|netz)\s+(?:nach\s+)?", "", query, flags=re.IGNORECASE
        )
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
        """Begrenzt Verlauf und Memory-Index für den semantischen Router."""
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
        """Validiert die JSON-Modellausgabe und baut eine IntentDecision."""
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
