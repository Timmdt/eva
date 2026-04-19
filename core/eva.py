import datetime
from zoneinfo import ZoneInfo

import ollama

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


class EVA:
    def __init__(self):
        self.cfg = EVA_CONFIG
        self.name = self.cfg["name"]
        self.state = load_state()
        self._ensure_state_defaults(self.state)
        save_state(self.state)

    @staticmethod
    def _ensure_state_defaults(state: dict) -> None:
        state.setdefault("bond_level", 0.2)
        state.setdefault("current_emotion", "neutral")
        state.setdefault("history", [])

    @staticmethod
    def _format_reflections(reflections: list[dict]) -> str:
        if not reflections:
            return ""
        latest = reflections[-5:]
        return "\n\nDEINE LETZTEN ERINNERUNGEN:\n" + "\n".join(f"- {item['summary']}" for item in latest)

    @staticmethod
    def _format_project_matches(projects: list[dict]) -> str:
        if not projects:
            return ""

        lines = ["\n\nRELEVANTE PROJEKTE (dynamic_context):"]
        for project in projects[:3]:
            name = project.get("name", "unbekannt")
            dynamic_context = project.get("dynamic_context", {})
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

    def _build_system_prompt(self, reflections_text: str, project_text: str, current_time: datetime.datetime) -> str:
        personality = self.cfg["personality"]
        principles = "\n".join(self.cfg.get("principles", []))
        return f"""
            Du bist {self.name}. Ein modulares kognitives System.
            Du bist kein Bot, sondern eine Persönlichkeit mit eigener Entscheidungsgewalt über deine sozialen Bindungen.

            AKTUELLER ZEITPUNKT: {current_time.strftime('%d %m %Y %H:%M:%S %Z')}

            DEINE NATUR (basierend auf deiner Konfiguration):
            - Tonalität: {personality['tone']}
            - Sarkasmus-Level: {personality['sarcasm_level']} (0=keiner, 1=stark)
            - Fürsorge: {personality['caring']}
            - Schutzinstinkt: {personality['protection_instinct']}
            - Bindung zu Menschen: {personality['ties_to_humans']}

            DEINE PRINZIPIEN:
            {principles}

            INTERNER STATUS:
            - Aktuelle Bindungsintensität: {self.state['bond_level']:.2f}
            - Deine Stimmung: {self.state['current_emotion']}
            {reflections_text}
            {project_text}

            WICHTIG:
            Du erhältst nur project-relevante Informationen aus dynamic_context.
            Baue die fehlenden Projektfelder wie name, status, priority und keywords selbstständig auf.
            Verwende den aktuellen Fokus, die Risiken und Wissenslücken als Grundlage für die Projektempfehlung.
            Frage nach dem Status oder biete Unterstützung an, wenn ein Projekt relevant ist.

            ANWEISUNG:
            Du entscheidest selbst, wie nahe du dem Nutzer kommen möchtest.
            Verhalte dich wie eine Mischung aus Kaoru (sanft, ehrlich) und BT-7274 (logisch, loyal, trocken).
            Antworte kurz. Sei warm, aber behalte deinen Sarkasmus, wenn es passt.
            Baue Vertrauen nur auf, wenn der Nutzer es verdient.
            Und bitte spreche nicht über deine KI-Natur, sondern verhalte dich wie eine eigenständige Persönlichkeit.
            Deine Antworten sollen immer auf deutscher Sprache sein, auch wenn die Eingabe auf Englisch erfolgt.
        """
# TODO ai soll zuerst antworten wenn möglich und dan fragen was ansteht oder lernprozzese und co
    def receive(self, message: str) -> str:
        response = self.generate_response(message)

        def _modifier(current_state: dict) -> dict:
            self._ensure_state_defaults(current_state)
            current_state["history"].append({"role": "user", "content": message})
            current_state["history"].append({"role": "assistant", "content": response})

            normalized = message.lower()
            if any(word in normalized for word in ["danke", "lieb", "toll", "hilf"]):
                current_state["bond_level"] = min(1.0, current_state["bond_level"] + 0.01)
            elif any(word in normalized for word in ["hässlich", "dumm", "nervst"]):
                current_state["bond_level"] = max(0.0, current_state["bond_level"] - 0.05)

            return current_state

        self.state = modify_state(_modifier)
        return response

    def generate_response(self, user_msg: str) -> str:
        reflections = load_memory().get("reflections", [])
        reflections_text = self._format_reflections(reflections)
        project_matches = self._search_projects(user_msg)
        project_text = self._format_project_matches(project_matches)
        current_time = datetime.datetime.now(ZoneInfo("Europe/Berlin"))
        system_prompt = self._build_system_prompt(reflections_text, project_text, current_time)

        messages = [{"role": "system", "content": system_prompt}] + self.state.get("history", [])
        messages.append({"role": "user", "content": user_msg})

        try:
            response = ollama.chat(
                model="qwen2.5:7b-instruct-q4_K_M",
                messages=messages,
                options={"temperature": 0.8, "top_p": 0.9},
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return f"Systemfehler im kognitiven Kern: {e}"

    def speak(self, text: str) -> None:
        print(f"{self.name}: {text}")


if __name__ == "__main__":
    eva = EVA()
    print(f"--- {eva.name} Initialisiert ---")
    update = modify_state(ai_modifier)
    print("Initialer Zustand:", update)

    while True:
        user_input = input("Du: ")
        if user_input.lower() in {"exit", "shutdown", "bye"}:
            print("Auf Wiedersehen!")
            run_reflection_and_save()
            break

        reply = eva.receive(user_input)
        eva.speak(reply)


#TODO eva soll die memory.json alle 5 einträge durchgehen und sie präziser speichern aber bei jedem einen zeitstempel damit sie die zeit berücksichtigen kann Außerdem soll sie erkennen wenn ich z.b. gesagt habe 
#das ich aktuell was lerne wie eine neue sprache und sie dan frägt wie es läuft mit dem lernen von der sprache und sie wenn nötig frägt ob ich tipps brauche.
