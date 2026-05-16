import datetime
import importlib
import logging
from zoneinfo import ZoneInfo
from typing import Any

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
        search_projects,
    )
except ImportError:
    from memory.memory_engine import (
        load_state,
        save_state,
        modify_state,
        ai_modifier,
        run_reflection_and_save,
        load_memory,
        search_projects,
    )

from module.base_module import ModuleBase

DEFAULT_MODULE_PATHS = [
    "module.jarvis_module",
    "module.test_module",
]
DEFAULT_TIMEZONE = "Europe/Berlin"
Message = dict[str, str]


class ModuleManager:
    """Lädt und steuert aktive EVA-Module."""

    def __init__(self, modules: list[ModuleBase]) -> None:
        self.modules = modules

    @classmethod
    def from_config(cls, config: dict[str, Any], eva_name: str) -> "ModuleManager":
        module_paths = config.get("modules", DEFAULT_MODULE_PATHS)
        loaded: list[ModuleBase] = []

        for module_path in module_paths:
            try:
                module_object = importlib.import_module(module_path)
            except Exception as exc:
                logging.exception("Konnte Modul %s nicht importieren: %s", module_path, exc)
                continue

            for attribute_name in dir(module_object):
                attribute = getattr(module_object, attribute_name)
                if (
                    isinstance(attribute, type)
                    and issubclass(attribute, ModuleBase)
                    and attribute is not ModuleBase
                ):
                    try:
                        loaded.append(attribute({"eva_name": eva_name}))
                    except Exception as exc:
                        logging.exception(
                            "Konnte Modulklasse %s nicht instanziieren: %s",
                            attribute_name,
                            exc,
                        )

        if not loaded:
            logging.warning("Keine Module geladen. Bitte überprüfe module_paths in config.")
        return cls(loaded)

    def module_names(self) -> list[str]:
        return [module.name for module in self.modules]

    def route(self, message: str, context: dict[str, Any]) -> str | None:
        for module in self.modules:
            try:
                if module.can_handle(message):
                    result = module.handle(message, context)
                    if isinstance(result, dict) and "text" in result:
                        return result["text"]
            except Exception as exc:
                logging.exception("Modul %s fehlgeschlagen: %s", module.name, exc)
        return None

    def run_startup_actions(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for module in self.modules:
            startup = getattr(module, "on_start", None)
            if not callable(startup):
                continue
            try:
                result = startup(context)
            except Exception as exc:
                logging.exception(
                    "Startup-Aktion in Modul %s fehlgeschlagen: %s",
                    module.name,
                    exc,
                )
                continue
            if isinstance(result, dict):
                actions.append(result)
        return actions

    def run_tests(self) -> list[tuple[bool, str]]:
        results: list[tuple[bool, str]] = []
        for module in self.modules:
            try:
                ok, msg = module.run_test()
            except Exception as exc:
                ok = False
                msg = f"{module.name} Testfehler: {exc}"
            results.append((ok, f"{module.name}: {msg}"))
        return results


class EVA:
    """Kernlogik von EVA mit Gedächtnis, Modulen und Sprachverarbeitung."""

    def __init__(self, run_module_tests: bool = True) -> None:
        self.cfg = EVA_CONFIG
        self.name = self.cfg.get("name", "EVA")
        self.state = load_state()
        self._ensure_state_defaults(self.state)
        self.module_manager = ModuleManager.from_config(self.cfg, self.name)
        self.startup_actions = self.module_manager.run_startup_actions(self._get_module_context())
        self.startup_message = self._resolve_startup_message(self.startup_actions)
        if self.startup_message:
            self._append_assistant_history(self.startup_message)

        if run_module_tests:
            self.module_test_results = self.run_module_tests()

        save_state(self.state)

    @staticmethod
    def _normalize_history(history: list[dict]) -> list[Message]:
        normalized: list[Message] = []
        for item in history or []:
            if not isinstance(item, dict):
                continue
            if "role" in item and "content" in item:
                normalized.append({"role": item["role"], "content": item["content"]})
                continue
            if "user" in item:
                normalized.append({"role": "user", "content": item["user"]})
            if "eva" in item:
                normalized.append({"role": "assistant", "content": item["eva"]})
        return normalized

    @staticmethod
    def _ensure_state_defaults(state: dict) -> None:
        state.setdefault("bond_level", 0.2)
        state.setdefault("current_emotion", "neutral")
        state.setdefault("history", [])
        state["history"] = EVA._normalize_history(state["history"])

    def _get_current_time(self) -> datetime.datetime:
        tz_name = self.cfg.get("timezone", DEFAULT_TIMEZONE)
        try:
            if tz_name.lower() == "local":
                return datetime.datetime.now().astimezone()
            return datetime.datetime.now(ZoneInfo(tz_name))
        except Exception:
            return datetime.datetime.now().astimezone()

    def _build_message_history(self) -> list[Message]:
        return self._normalize_history(self.state.get("history", []))

    def _get_module_context(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "module_names": self.module_manager.module_names(),
        }

    def _resolve_startup_message(self, actions: list[dict[str, Any]]) -> str | None:
        for action in actions:
            if action.get("startup_memory"):
                return self._generate_startup_message(action["startup_memory"])
            if action.get("fallback_text"):
                return action["fallback_text"]
            text = action.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
        return None

    def _append_assistant_history(self, assistant_text: str) -> None:
        def _modifier(current_state: dict) -> dict:
            self._ensure_state_defaults(current_state)
            history = current_state.setdefault("history", [])
            history.append({"role": "assistant", "content": assistant_text})
            return current_state

        self.state = modify_state(_modifier)

    def _build_system_prompt(
        self, reflections_text: str, project_index: str, current_time: datetime.datetime
    ) -> str:
        module_names = ", ".join(self.module_manager.module_names()) or "keine Module"
        return f"""
                Du bist {self.name}. Ein modulares, assistierendes System im Stil von JARVIS.
                Verhalte dich freundlich, humorvoll und sachlich zugleich. Helfe mit klarem Fokus auf Sicherheit, Transparenz und einfache Bedienung.

                ZEITPUNKT: {current_time.strftime('%d.%m.%Y %H:%M:%S %Z')}
                STATUS: Bond {self.state['bond_level']:.2f} | Stimmung: {self.state['current_emotion']}

                VERFÜGBARE MODULE:
                {module_names}
                {project_index}
                {reflections_text}

                REGELN:
                - Antworte ehrlich. Wenn du etwas nicht weißt, sag es klar.
                - Nutze den bisherigen Gesprächsverlauf als Kontext. Beziehe dich auf frühere Aussagen, insbesondere auf Projekte, Erinnerungen und Ziele.
                - Nutze keine Fakten, die du nicht sichern kannst.
                - Wenn ein Thema in einem geladenen Modul besser aufgehoben ist, leite dorthin.
                - Wenn du einen externen Dienst brauchst, erkläre kurz, was du abrufst.
                - Halte die Antwort kurz und nutzerfreundlich.
                """

    def _build_startup_prompt(self, startup_memory: dict[str, Any]) -> str:
        parts: list[str] = [
            "Hier sind einige Erinnerungen aus dem Langzeitgedächtnis von EVA. Generiere eine freundliche, natürliche Startnachricht für den Benutzer.",
            "Verwende keinen Aufzählungsstil und formuliere es so, dass es wie ein persönlicher Reminder klingt.",
        ]

        if startup_memory.get("important_point"):
            parts.append(f"Wichtige Erinnerung: {startup_memory['important_point']}")
        if startup_memory.get("project"):
            project = startup_memory["project"]
            name = project.get("name", "ein Projekt")
            status = project.get("status", "in Arbeit")
            context_data = project.get("dynamic_context", {}) or {}
            focus = (
                context_data.get("current_focus")
                or context_data.get("focus")
                or "daran, das weiterzuverfolgen"
            )
            parts.append(
                f"Projekt: {name}, Status {status}, Fokus: {focus}."
            )
        if startup_memory.get("learning_goal"):
            parts.append(f"Lernziel: {startup_memory['learning_goal']}")

        parts.append("Antworte nur mit der Nachricht, keinen Systemtext.")
        return "\n".join(parts)

    def _generate_startup_message(self, startup_memory: dict[str, Any]) -> str:
        if not startup_memory or ollama is None:
            return self._fallback_startup_text(startup_memory)

        prompt = self._build_startup_prompt(startup_memory)
        try:
            response = ollama.chat(
                model="mistral-nemo:12b-instruct-2407-q4_K_S",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Erstelle eine freundliche Startnachricht."},
                ],
                options={"temperature": 0.4, "top_p": 0.9},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            logging.exception("Startup-Ollama-Anfrage fehlgeschlagen.", exc_info=e)
            return self._fallback_startup_text(startup_memory)

    def _fallback_startup_text(self, startup_memory: dict[str, Any]) -> str:
        if not startup_memory:
            return (
                "Guten Start! Ich habe im Moment keine dringenden Erinnerungen oder Lernziele, "
                "die ich dir nennen sollte. Sag mir einfach, was du als Nächstes angehen willst."
            )

        parts: list[str] = []
        if startup_memory.get("important_point"):
            parts.append(f"Hi, ich erinnere dich kurz an: {startup_memory['important_point']}.")
        if startup_memory.get("project"):
            project = startup_memory["project"]
            name = project.get("name", "dein Projekt")
            status = project.get("status", "in Arbeit")
            context_data = project.get("dynamic_context", {}) or {}
            focus = (
                context_data.get("current_focus")
                or context_data.get("focus")
                or "das weiterzuverfolgen"
            )
            parts.append(
                f"Aktuell läuft dein Projekt '{name}' {status}. Wie geht es dir damit?"
            )
        if not startup_memory.get("project") and startup_memory.get("learning_goal"):
            parts.append(
                f"Dein nächstes Lernziel war: {startup_memory['learning_goal']}. Wenn du willst, können wir heute damit starten."
            )
        return " ".join(parts) if parts else (
            "Guten Start! Ich habe im Moment keine dringenden Erinnerungen oder Lernziele, "
            "die ich dir nennen sollte. Sag mir einfach, was du als Nächstes angehen willst."
        )

    def _format_reflections(self, reflections: list[dict]) -> str:
        if not reflections:
            return ""
        latest = reflections[-5:]
        return "\n\nDEINE LETZTEN ERINNERUNGEN:\n" + "\n".join(
            f"- {item.get('summary', '')}" for item in latest
        )

    def _format_project_matches(self, projects: list[dict]) -> str:
        if not projects:
            return ""

        lines = ["\n\nRELEVANTE PROJEKTE (dynamic_context):"]
        for project in projects[:3]:
            name = project.get("name", "unbekannt")
            dynamic_context = project.get("dynamic_context", {}) or {}
            current_focus = dynamic_context.get("current_focus", "keine Angabe")
            critical_fear = dynamic_context.get("critical_fear", "keine Angabe")
            knowledge_gaps = dynamic_context.get("knowledge_gaps", [])
            lines.append(
                f"- Projekt: {name} | Fokus: {current_focus} | Risiko: {critical_fear} | Wissenslücken: {', '.join(knowledge_gaps) if knowledge_gaps else 'keine Angabe'}"
            )
        return "\n".join(lines)

    def _search_projects(self, query: str) -> list[dict]:
        memory = load_memory()
        if not query:
            return []
        return search_projects(
            memory,
            query,
            fields=[
                "dynamic_context.current_focus",
                "dynamic_context.critical_fear",
                "dynamic_context.knowledge_gaps",
                "name",
            ],
        )

    def _append_history(self, user_text: str, eva_text: str) -> None:
        def _modifier(current_state: dict) -> dict:
            self._ensure_state_defaults(current_state)
            history = current_state.setdefault("history", [])
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": eva_text})
            return current_state

        self.state = modify_state(_modifier)

    def receive(self, message: str) -> str:
        module_response = self.module_manager.route(message, self._get_module_context())
        if module_response:
            self._append_history(message, module_response)
            return module_response

        response = self.generate_response(message)
        self._append_history(message, response)
        return response

    def generate_response(self, user_msg: str) -> str:
        reflections = load_memory().get("reflections", [])
        reflections_text = self._format_reflections(reflections)
        project_matches = self._search_projects(user_msg)
        project_text = self._format_project_matches(project_matches)
        current_time = self._get_current_time()
        system_prompt = self._build_system_prompt(reflections_text, project_text, current_time)

        messages = [{"role": "system", "content": system_prompt}] + self._build_message_history()
        messages.append({"role": "user", "content": user_msg})

        if ollama is None:
            return (
                "Ollama ist nicht verfügbar. Bitte installiere ollama oder nutze den lokalen Modus. "
                "Ich bin bereit, wenn die Umgebung eingerichtet ist."
            )

        try:
            response = ollama.chat(
                model="mistral-nemo:12b-instruct-2407-q4_K_S",
                messages=messages,
                options={"temperature": 0.2, "top_p": 0.9},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            logging.exception("Ollama-Anfrage fehlgeschlagen.", exc_info=e)
            return f"Systemfehler im kognitiven Kern: {e}"

    def run_module_tests(self) -> list[tuple[bool, str]]:
        results = self.module_manager.run_tests()
        for ok, msg in results:
            status = "OK" if ok else "FEHLER"
            print(f"[Modultest] {status} - {msg}")
        return results

    def shutdown(self) -> None:
        run_reflection_and_save()

    def startup(self) -> str | None:
        return self.startup_message

    def speak(self, text: str) -> None:
        print(f"{self.name}: {text}")


if __name__ == "__main__":
    eva = EVA()
    print(f"--- {eva.name} Initialisiert ---")
    update = modify_state(ai_modifier)
    print("Initialer Zustand:", update)

    try:
        while True:
            user_input = input("Du: ")
            if user_input.lower() in {"exit", "shutdown", "bye"}:
                print("Auf Wiedersehen!")
                eva.shutdown()
                break

            reply = eva.receive(user_input)
            eva.speak(reply)
    except KeyboardInterrupt:
        print("\nBeendet.")
        eva.shutdown()
