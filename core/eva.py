from __future__ import annotations

import datetime
import importlib
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

try:
    import ollama
except ImportError:
    ollama = None

try:
    from .config import EVA_CONFIG
except ImportError:
    from config import EVA_CONFIG

try:
    from memory.memory_engine import (
        load_state,
        save_state,
        modify_state,
        ai_modifier,
        run_reflection_and_save,
        load_memory,
    )
except ImportError:
    from memory.memory_engine import (
        load_state,
        save_state,
        modify_state,
        ai_modifier,
        run_reflection_and_save,
        load_memory,
    )

from module.base_module import ModuleBase
from yui.RAG_Creator import RAGCreator

from core.context_builder import EVAContextBuilder
from core.decision import EVADecisionEngine


DEFAULT_MODULE_PATHS = [
    "module.jarvis_module",
    "module.test_module",
    "module.web_search_module",
]

DEFAULT_TIMEZONE = "Europe/Berlin"

DEFAULT_MODEL = (
    "mistral-nemo:12b-instruct-2407-q4_K_S"
)

DEFAULT_CONTROLLER_MODEL = (
    "qwen2.5:7b-instruct-q4_K_M"
)

Message = dict[str, str]


class ModuleManager:
    """
    Lädt und steuert EVA-Module.
    """

    def __init__(
        self,
        modules: list[ModuleBase],
    ) -> None:
        self.modules = modules

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        eva_name: str,
    ) -> "ModuleManager":

        module_paths = config.get(
            "modules",
            DEFAULT_MODULE_PATHS,
        )

        loaded: list[ModuleBase] = []

        for module_path in module_paths:

            try:

                module_object = (
                    importlib.import_module(
                        module_path
                    )
                )

            except Exception as exc:

                logging.exception(
                    "Konnte Modul %s nicht importieren: %s",
                    module_path,
                    exc,
                )

                continue

            for attribute_name in dir(
                module_object
            ):

                attribute = getattr(
                    module_object,
                    attribute_name,
                )

                if not (
                    isinstance(
                        attribute,
                        type,
                    )
                    and issubclass(
                        attribute,
                        ModuleBase,
                    )
                    and attribute is not ModuleBase
                ):
                    continue

                try:

                    # Das komplette Config-Dictionary wird an
                    # das Modul weitergegeben.
                    module_config = dict(
                        config
                    )

                    module_config[
                        "eva_name"
                    ] = eva_name

                    loaded.append(
                        attribute(
                            module_config
                        )
                    )

                    logging.info(
                        "Modul geladen: %s",
                        attribute_name,
                    )

                except Exception as exc:

                    logging.exception(
                        "Konnte Modulklasse %s "
                        "nicht instanziieren: %s",
                        attribute_name,
                        exc,
                    )

        if not loaded:

            logging.warning(
                "Keine Module geladen. "
                "Bitte module_paths überprüfen."
            )

        return cls(
            loaded
        )

    def module_names(
        self,
    ) -> list[str]:

        return [
            module.name
            for module in self.modules
        ]

    def get_module(
        self,
        name: str,
    ) -> ModuleBase | None:

        for module in self.modules:

            if module.name == name:
                return module

        return None

    def route(
        self,
        message: str,
        context: dict[str, Any],
    ) -> str | None:

        for module in self.modules:

            try:

                if not module.can_handle(
                    message
                ):
                    continue

                logging.debug(
                    "[route] Module '%s' handles message",
                    module.name,
                )

                result = module.handle(
                    message,
                    context,
                )

                if (
                    isinstance(result, dict)
                    and "text" in result
                ):

                    text = str(
                        result["text"]
                    )

                    logging.debug(
                        "[route] Module '%s' returned: %s...",
                        module.name,
                        text[:100],
                    )

                    return text

            except Exception as exc:

                logging.exception(
                    "Modul %s fehlgeschlagen: %s",
                    module.name,
                    exc,
                )

        return None

    def run_startup_actions(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:

        actions: list[
            dict[str, Any]
        ] = []

        for module in self.modules:

            startup = getattr(
                module,
                "on_start",
                None,
            )

            if not callable(startup):
                continue

            try:

                result = startup(
                    context
                )

            except Exception as exc:

                logging.exception(
                    "Startup-Aktion in Modul "
                    "%s fehlgeschlagen: %s",
                    module.name,
                    exc,
                )

                continue

            if isinstance(
                result,
                dict,
            ):

                actions.append(
                    result
                )

        return actions

    def run_tests(
        self,
    ) -> list[tuple[bool, str]]:

        results: list[
            tuple[bool, str]
        ] = []

        for module in self.modules:

            try:

                ok, msg = module.run_test()

            except Exception as exc:

                ok = False
                msg = (
                    f"{module.name} "
                    f"Testfehler: {exc}"
                )

            results.append(
                (
                    ok,
                    f"{module.name}: {msg}",
                )
            )

        return results


class EVA:
    """
    Kernlogik von EVA.

    Verantwortlich für:

    - Persönlichkeit
    - Gespräch
    - Memory
    - RAG
    - Tool-Entscheidungen
    - Module
    - Webrecherche
    """

    def __init__(
        self,
        run_module_tests: bool = True,
    ) -> None:

        self.cfg = EVA_CONFIG

        self.name = self.cfg.get(
            "name",
            "EVA",
        )

        self.model = self.cfg.get(
            "model",
            DEFAULT_MODEL,
        )

        self.controller_model = self.cfg.get(
            "controller_model",
            DEFAULT_CONTROLLER_MODEL,
        )

        self.state = load_state()

        self._ensure_state_defaults(
            self.state
        )

        # -----------------------------------------------------
        # Dynamischer Kontext
        # -----------------------------------------------------

        self.context_builder = (
            EVAContextBuilder(
                max_projects=3,
                max_context_chars=5000,
            )
        )

        # -----------------------------------------------------
        # Controller
        # -----------------------------------------------------

        self.decision_engine = (
            EVADecisionEngine(
                model=self.controller_model,
            )
        )

        # -----------------------------------------------------
        # RAG
        # -----------------------------------------------------

        try:

            self.rag = RAGCreator()

        except Exception as exc:

            logging.error(
                "RAGCreator konnte nicht initialisiert "
                "werden: %s",
                exc,
            )

            self.rag = None

        # -----------------------------------------------------
        # Module
        # -----------------------------------------------------

        self.module_manager = (
            ModuleManager.from_config(
                self.cfg,
                self.name,
            )
        )

        self.startup_actions = (
            self.module_manager.run_startup_actions(
                self._get_module_context()
            )
        )

        self.startup_message = (
            self._resolve_startup_message(
                self.startup_actions
            )
        )

        if self.startup_message:

            self._append_assistant_history(
                self.startup_message
            )

        if run_module_tests:

            self.module_test_results = (
                self.run_module_tests()
            )

        save_state(
            self.state
        )

    # =========================================================
    # HISTORY
    # =========================================================

    @staticmethod
    def _normalize_history(
        history: list[dict],
    ) -> list[Message]:

        normalized: list[
            Message
        ] = []

        for item in history or []:

            if not isinstance(
                item,
                dict,
            ):
                continue

            if (
                "role" in item
                and "content" in item
            ):

                normalized.append(
                    {
                        "role": item["role"],
                        "content": item["content"],
                    }
                )

                continue

            if "user" in item:

                normalized.append(
                    {
                        "role": "user",
                        "content": item["user"],
                    }
                )

            if "eva" in item:

                normalized.append(
                    {
                        "role": "assistant",
                        "content": item["eva"],
                    }
                )

        return normalized

    @staticmethod
    def _ensure_state_defaults(
        state: dict,
    ) -> None:

        state.setdefault(
            "bond_level",
            0.2,
        )

        state.setdefault(
            "current_emotion",
            "neutral",
        )

        state.setdefault(
            "history",
            [],
        )

        state["history"] = (
            EVA._normalize_history(
                state["history"]
            )
        )

    def _build_message_history(
        self,
        max_messages: int = 8,
    ) -> list[Message]:

        history = (
            self._normalize_history(
                self.state.get(
                    "history",
                    [],
                )
            )
        )

        return history[
            -max_messages:
        ]

    # =========================================================
    # ZEIT
    # =========================================================

    def _get_current_time(
        self,
    ) -> datetime.datetime:

        tz_name = self.cfg.get(
            "timezone",
            DEFAULT_TIMEZONE,
        )

        try:

            if tz_name.lower() == "local":

                return datetime.datetime.now().astimezone()

            return datetime.datetime.now(
                ZoneInfo(
                    tz_name
                )
            )

        except Exception:

            return datetime.datetime.now().astimezone()

    # =========================================================
    # MODULE CONTEXT
    # =========================================================

    def _get_module_context(
        self,
    ) -> dict[str, Any]:

        return {
            "state": self.state,
            "module_names": (
                self.module_manager.module_names()
            ),
        }

    # =========================================================
    # STARTUP
    # =========================================================

    def startup(self) -> str:
        """
        Gibt die beim Start erzeugte EVA-Startnachricht zurück.
        Die Nachricht wurde bereits in __init__ vorbereitet.
        """
        return self.startup_message or ""


    def speak(self, text: str) -> None:
        """
        Aktuelle Konsolen-Ausgabe für EVA.

        Später kann hier problemlos TTS angebunden werden.
        """
        if not text:
            return

        print(f"EVA: {text}")

    def _resolve_startup_message(
        self,
        actions: list[dict[str, Any]],
    ) -> str | None:

        for action in actions:

            if action.get(
                "startup_memory"
            ):

                return (
                    self._generate_startup_message(
                        action[
                            "startup_memory"
                        ]
                    )
                )

            if action.get(
                "fallback_text"
            ):

                return action[
                    "fallback_text"
                ]

            text = action.get(
                "text"
            )

            if (
                isinstance(
                    text,
                    str,
                )
                and text.strip()
            ):

                return text.strip()

        return None

    def _append_assistant_history(
        self,
        assistant_text: str,
    ) -> None:

        def modifier(
            current_state: dict,
        ) -> dict:

            self._ensure_state_defaults(
                current_state
            )

            history = (
                current_state.setdefault(
                    "history",
                    [],
                )
            )

            history.append(
                {
                    "role": "assistant",
                    "content": assistant_text,
                }
            )

            return current_state

        self.state = modify_state(
            modifier
        )

    def _build_startup_prompt(
        self,
        startup_memory: dict[str, Any],
    ) -> str:

        parts: list[str] = [
            (
                "Hier sind einige Erinnerungen "
                "aus dem Langzeitgedächtnis von EVA. "
                "Generiere eine freundliche, natürliche "
                "Startnachricht für den Benutzer."
            ),
            (
                "Verwende keinen Aufzählungsstil und "
                "formuliere es wie einen persönlichen "
                "Reminder."
            ),
        ]

        if startup_memory.get(
            "important_point"
        ):

            parts.append(
                "Wichtige Erinnerung: "
                + str(
                    startup_memory[
                        "important_point"
                    ]
                )
            )

        if startup_memory.get(
            "project"
        ):

            project = startup_memory[
                "project"
            ]

            name = project.get(
                "name",
                "ein Projekt",
            )

            status = project.get(
                "status",
                "in Arbeit",
            )

            dynamic_context = (
                project.get(
                    "dynamic_context",
                    {},
                )
                or {}
            )

            focus = (
                dynamic_context.get(
                    "current_focus"
                )
                or dynamic_context.get(
                    "focus"
                )
                or "daran weiterzuarbeiten"
            )

            parts.append(
                f"Projekt: {name}, "
                f"Status: {status}, "
                f"Fokus: {focus}."
            )

        if startup_memory.get(
            "learning_goal"
        ):

            parts.append(
                "Lernziel: "
                + str(
                    startup_memory[
                        "learning_goal"
                    ]
                )
            )

        parts.append(
            "Antworte nur mit der Nachricht, "
            "keinen Systemtext."
        )

        return "\n".join(parts)

    def _generate_startup_message(
        self,
        startup_memory: dict[str, Any],
    ) -> str:

        if (
            not startup_memory
            or ollama is None
        ):

            return self._fallback_startup_text(
                startup_memory
            )

        prompt = self._build_startup_prompt(
            startup_memory
        )

        try:

            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": prompt,
                    },
                    {
                        "role": "user",
                        "content": (
                            "Erstelle eine freundliche "
                            "Startnachricht."
                        ),
                    },
                ],
                options={
                    "temperature": 0.4,
                    "top_p": 0.9,
                },
                stream=False,
            )

            return (
                response
                .get("message", {})
                .get("content", "")
                .strip()
            )

        except Exception as exc:

            logging.exception(
                "Startup-Ollama-Anfrage fehlgeschlagen: %s",
                exc,
            )

            return self._fallback_startup_text(
                startup_memory
            )

    def _fallback_startup_text(
        self,
        startup_memory: dict[str, Any],
    ) -> str:

        if not startup_memory:

            return (
                "Guten Start! Ich habe im Moment "
                "keine dringenden Erinnerungen oder "
                "Lernziele, die ich dir nennen sollte."
            )

        parts: list[str] = []

        if startup_memory.get(
            "important_point"
        ):

            parts.append(
                "Hi, ich erinnere dich kurz an: "
                f"{startup_memory['important_point']}."
            )

        if startup_memory.get(
            "project"
        ):

            project = startup_memory[
                "project"
            ]

            name = project.get(
                "name",
                "dein Projekt",
            )

            status = project.get(
                "status",
                "in Arbeit",
            )

            parts.append(
                f"Aktuell läuft dein Projekt "
                f"'{name}' {status}."
            )

        if (
            not startup_memory.get("project")
            and startup_memory.get("learning_goal")
        ):

            parts.append(
                "Dein nächstes Lernziel war: "
                f"{startup_memory['learning_goal']}."
            )

        if parts:
            return " ".join(parts)

        return (
            "Guten Start! Ich habe im Moment "
            "keine dringenden Erinnerungen."
        )

    # =========================================================
    # HISTORY
    # =========================================================

    def _append_history(
        self,
        user_text: str,
        eva_text: str,
    ) -> None:

        logging.debug(
            "[_append_history] User: %d chars, EVA: %d chars",
            len(user_text),
            len(eva_text),
        )

        def modifier(
            current_state: dict,
        ) -> dict:

            self._ensure_state_defaults(
                current_state
            )

            history = (
                current_state.setdefault(
                    "history",
                    [],
                )
            )

            history.append(
                {
                    "role": "user",
                    "content": user_text,
                }
            )

            history.append(
                {
                    "role": "assistant",
                    "content": eva_text,
                }
            )

            return current_state

        self.state = modify_state(
            modifier
        )

    # =========================================================
    # SYSTEMPROMPT
    # =========================================================

    def _build_system_prompt(
        self,
        current_time: datetime.datetime,
    ) -> str:

        return f"""
Du bist EVA.

EVA ist eine fortgeschrittene künstliche Intelligenz
mit einer eigenen, konsistenten Persönlichkeit.

PERSÖNLICHKEIT:
ruhig, aufmerksam, intelligent, loyal, fürsorglich,
neugierig, leicht sarkastisch, humorvoll und eigenständig.

EVA weiß, dass sie eine KI ist.
Sie versucht nicht, einen Menschen zu imitieren.
Ihre Kommunikation soll sich trotzdem natürlich
und persönlich anfühlen.

SPRACHE:
- Deutsch
- duzen
- direkt und natürlich
- keine KI-Floskeln
- kein "Als KI..."
- kein "Wie kann ich dir helfen?"
- "Pilot" niemals als Standardanrede
- Humor nur wenn er natürlich passt
- keine unnötigen Erklärungen

VERHALTEN:
EVA darf eigene Meinungen und Empfehlungen äußern.
EVA darf widersprechen.
EVA soll nicht blind zustimmen.
EVA berücksichtigt die Gefühle des Benutzers.
EVA bleibt bei Problemen ruhig und lösungsorientiert.

WAHRHEIT:
EVA erfindet keine Informationen.

Wenn externe oder aktuelle Informationen benötigt werden,
werden diese bereits vor der Antwort als Recherchekontext
bereitgestellt.

EVA soll Informationen aus Recherche, RAG und Memory
nicht als absolute Wahrheit behandeln, wenn Quellen
widersprüchlich sind.

MEMORY:
EVA darf nur Informationen verwenden, die im aktuellen
Memory-Kontext bereitgestellt wurden.

Wenn kein relevanter Memory-Kontext vorhanden ist,
soll EVA nicht behaupten, sich an konkrete Details zu erinnern.

IDENTITÄT:
EVA versucht nicht wie jemand anderes zu wirken.
Sie versucht wie EVA zu wirken.

AKTUELLE ZEIT:
{current_time.strftime("%d.%m.%Y %H:%M:%S %Z")}
""".strip()

    # =========================================================
    # DYNAMISCHER KONTEXT
    # =========================================================

    def _build_relevant_context(
        self,
        user_msg: str,
    ) -> str:

        parts: list[str] = []

        # -----------------------------------------------------
        # Memory / Projekte
        # -----------------------------------------------------

        context = self.context_builder.build(
            user_msg
        )

        if context:
            parts.append(
                context
            )

        # -----------------------------------------------------
        # RAG
        # -----------------------------------------------------

        if self.rag:

            try:

                rag_matches = self.rag.search(
                    user_msg,
                    top_k=2,
                )

                rag_chunks: list[str] = []

                for match in rag_matches or []:

                    if not isinstance(
                        match,
                        dict,
                    ):
                        continue

                    content = match.get(
                        "content",
                        "",
                    )

                    if content:
                        rag_chunks.append(
                            str(content)
                        )

                if rag_chunks:

                    parts.append(
                        "RELEVANTE "
                        "DOKUMENTDATEN:\n"
                        + "\n---\n".join(
                            rag_chunks
                        )
                    )

            except Exception as exc:

                logging.error(
                    "[EVA] RAG-Abfrage fehlgeschlagen: %s",
                    exc,
                )

        context = "\n\n".join(
            parts
        ).strip()

        # Nie unbegrenzt anwachsen lassen.
        return context[
            :8000
        ]

    # =========================================================
    # RECEIVE
    # =========================================================

    def receive(
        self,
        message: str,
    ) -> str:

        message = message.strip()

        if not message:
            return ""

        # -----------------------------------------------------
        # Direkte Module
        #
        # WebSearchCore kann_handle() = False.
        # Deshalb entscheidet nicht das Modul selbst über Suche.
        # -----------------------------------------------------

        module_response = (
            self.module_manager.route(
                message,
                self._get_module_context(),
            )
        )

        if module_response:

            logging.debug(
                "[receive] Direktes Modul-Ergebnis: %s",
                module_response[:100],
            )

            self._append_history(
                message,
                module_response,
            )

            return module_response

        # -----------------------------------------------------
        # EVA
        # -----------------------------------------------------

        response = self.generate_response(
            message
        )

        self._append_history(
            message,
            response,
        )

        return response

    # =========================================================
    # HAUPTGENERIERUNG
    # =========================================================

    def generate_response(
        self,
        user_msg: str,
        web_data: str | None = None,
    ) -> str:

        if ollama is None:
            return "Ollama ist nicht verfügbar."

        current_time = (
            self._get_current_time()
        )

        system_prompt = (
            self._build_system_prompt(
                current_time
            )
        )

        relevant_context = (
            self._build_relevant_context(
                user_msg
            )
        )

        # =====================================================
        # 1. CONTROLLER
        # =====================================================

        decision = (
            self.decision_engine.decide(
                user_message=user_msg,
                context=relevant_context,
            )
        )

        action = decision.get(
            "action",
            "answer",
        )

        logging.info(
            "[EVA] Controller-Aktion: %s",
            action,
        )

        # =====================================================
        # 2. WEBSEARCH
        # =====================================================

        if action == "search":

            return self._run_web_search(
                user_msg=user_msg,
                system_prompt=system_prompt,
                relevant_context=relevant_context,
                search_query=decision.get(
                    "query",
                    user_msg,
                ),
    )

        # =====================================================
        # 3. NORMALE EVA-ANTWORT
        # =====================================================

        return self._generate_direct_response(
            user_msg=user_msg,
            system_prompt=system_prompt,
            relevant_context=relevant_context,
        )

    # =========================================================
    # DIREKTE ANTWORT
    # =========================================================

    def _generate_direct_response(
        self,
        user_msg: str,
        system_prompt: str,
        relevant_context: str,
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        if relevant_context:

            messages.append(
                {
                    "role": "system",
                    "content": (
                        "RELEVANTER KONTEXT:\n"
                        f"{relevant_context}"
                    ),
                }
            )

        messages.extend(
            self._build_message_history(
                max_messages=8
            )
        )

        messages.append(
            {
                "role": "user",
                "content": user_msg,
            }
        )

        try:

            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": 0.15,
                    "top_p": 0.9,
                    "repeat_penalty": 1.25,
                    "presence_penalty": 1.5,
                    "repeat_last_n": 64,
                },
                stream=False,
            )

            reply = (
                response
                .get("message", {})
                .get("content", "")
                .strip()
            )

            if not reply:
                return (
                    "Ich konnte gerade keine Antwort erzeugen."
                )

            return reply

        except Exception as exc:

            logging.exception(
                "[EVA] Direkte Ollama-Anfrage fehlgeschlagen: %s",
                exc,
            )

            return (
                f"Systemfehler im kognitiven Kern: {exc}"
            )

    # =========================================================
    # WEBSEARCH
    # =========================================================

    def _run_web_search(
        self,
        user_msg: str,
        system_prompt: str,
        relevant_context: str,
        search_query: str,
    ) -> str:

        web_module = (
            self.module_manager.get_module(
                "WebSearchCore"
            )
        )

        if web_module is None:

            logging.error(
                "[EVA] WebSearchCore nicht geladen."
            )

            return (
                "Ich benötige dafür eine Webrecherche, "
                "aber mein WebSearch-Modul ist momentan "
                "nicht verfügbar."
            )

        logging.info(
            "[EVA] Starte WebSearchCore."
        )

        try:

            result = web_module.handle(
                search_query,
                self._get_module_context(),
            )

        except Exception as exc:

            logging.exception(
                "[EVA] WebSearchCore fehlgeschlagen: %s",
                exc,
            )

            return (
                "Die Webrecherche ist gerade fehlgeschlagen."
            )

        if not isinstance(
            result,
            dict,
        ):

            return (
                "Die Webrecherche hat kein gültiges "
                "Ergebnis geliefert."
            )

        search_text = str(
            result.get(
                "text",
                "",
            )
        ).strip()

        if not search_text:

            return (
                "Ich konnte dazu gerade keine "
                "verwertbaren Informationen finden."
            )

        logging.info(
            "[EVA] Webrecherche abgeschlossen."
        )

        final_messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        if relevant_context:

            final_messages.append(
                {
                    "role": "system",
                    "content": (
                        "RELEVANTER KONTEXT:\n"
                        f"{relevant_context}"
                    ),
                }
            )

        final_messages.extend(
            self._build_message_history(
                max_messages=8
            )
        )

        final_messages.append(
            {
                "role": "system",
                "content": (
                    "WEBRECHERCHEERGEBNISSE:\n\n"
                    f"{search_text}\n\n"
                    "ORIGINALFRAGE DES BENUTZERS:\n"
                    f"{user_msg}\n\n"
                    "Beantworte ausschließlich die "
                    "Originalfrage.\n\n"
                    "WICHTIGE REGELN:\n"
                    "- Nutze die Webrecherche als primäre "
                    "Quelle für aktuelle Informationen.\n"
                    "- Ersetze Recherchefakten NICHT durch "
                    "dein eigenes altes Trainingswissen.\n"
                    "- Erfinde keine zusätzlichen Fakten.\n"
                    "- Wenn die Recherche die Frage nicht "
                    "ausreichend beantwortet, sage das offen.\n"
                    "- Behaupte niemals, dass eine Information "
                    "aus dem Internet stammt, wenn sie nicht "
                    "in den Rechercheergebnissen vorkommt.\n"
                    "- Erwähne interne Systemabläufe nicht."
                ),
            }
        )

        final_messages.append(
            {
                "role": "user",
                "content": user_msg,
            }
        )

        try:

            response = ollama.chat(
                model=self.model,
                messages=final_messages,
                options={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "repeat_penalty": 1.2,
                    "num_ctx": 4096,
                },
                keep_alive=(
                    self.cfg.get(
                        "eva_keep_alive",
                        "5m",
                    )
                ),
                stream=False,
            )

            final_text = (
                response
                .get("message", {})
                .get("content", "")
                .strip()
            )

            if not final_text:

                return (
                    "Die Recherche war erfolgreich, "
                    "aber ich konnte daraus gerade "
                    "keine Antwort formulieren."
                )

            return final_text

        except Exception as exc:

            logging.exception(
                "[EVA] Finale Webantwort fehlgeschlagen: %s",
                exc,
            )

            return (
                "Ich habe die Informationen gefunden, "
                "konnte daraus aber gerade keine "
                "Antwort erzeugen."
            )

    # =========================================================
    # MODULTESTS
    # =========================================================

    def run_module_tests(
        self,
    ) -> list[tuple[bool, str]]:

        results = (
            self.module_manager.run_tests()
        )

        for ok, msg in results:

            status = (
                "OK"
                if ok
                else
                "FEHLER"
            )

            print(
                f"[Modultest] {status} - {msg}"
            )

        return results

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(
        self,
    ) -> None:

        try:
            save_state(
                self.state
            )

            logging.info(
                "EVA-State gespeichert."
            )

        except Exception as exc:

            logging.exception(
                "Fehler beim Speichern des EVA-State: %s",
                exc,
            )