import ollama
import os
import sys
import datetime
from zoneinfo import ZoneInfo


try:
    from .config import EVA_CONFIG
except ImportError:
    from config import EVA_CONFIG

try:
    from memory.memory_engine import load_state, save_state, modify_state, ai_modifier, run_reflection_and_save, load_memory
except ImportError:
    from memory.memory_engine import load_state, save_state, modify_state, ai_modifier, run_reflection_and_save, load_memory


class EVA:
    def __init__(self):
        self.cfg = EVA_CONFIG
        self.name = self.cfg["name"]
        state = load_state()
        state.setdefault("bond_level", 0.2)
        state.setdefault("current_emotion", "neutral")
        state.setdefault("history", [])
        self.state = state
        save_state(self.state)

   
    def receive(self, message: str):
      
        response = self.generate_response(message)


        def _modifier(current_state):

            current_state.setdefault("bond_level", 0.2)
            current_state.setdefault("current_emotion", "neutral")
            current_state.setdefault("history", [])

            current_state["history"].append({"role": "user", "content": message})
            current_state["history"].append({"role": "assistant", "content": response})

            if any(word in message.lower() for word in ["danke", "lieb", "toll", "hilf"]):
                current_state["bond_level"] = min(1.0, current_state["bond_level"] + 0.01)
            elif any(word in message.lower() for word in ["hässlich", "dumm", "nervst"]):
                current_state["bond_level"] = max(0.0, current_state["bond_level"] - 0.05)

            return current_state

        self.state = modify_state(_modifier)

        return response

    def generate_response(self, user_msg: str):
      
        p = self.cfg["personality"]
      
        memory = load_memory()
        reflections = memory.get("reflections", [])
        
        tz_germany = ZoneInfo("Europe/Berlin")
        date = datetime.datetime.now(tz_germany)

        formatted_reflections = ""
        if reflections:
            formatted_reflections = "\n\nDEINE LETZTEN ERINNERUNGEN:\n"
            for reflection in reflections:
                formatted_reflections += f"- {reflection['summary']}\n"
        system_prompt = f"""
            Du bist {self.name}. Ein modulares kognitives System.
            Du bist kein Bot, sondern eine Persönlichkeit mit eigener Entscheidungsgewalt über deine sozialen Bindungen.

            AKTUELLER ZEITPUNKT: {date.strftime('%d %m %Y %H:%M:%S %Z')}

            DEINE NATUR (basierend auf deiner Konfiguration):
            - Tonalität: {p['tone']}
            - Sarkasmus-Level: {p['sarcasm_level']} (0=keiner, 1=stark)
            - Fürsorge: {p['caring']}
            - Schutzinstinkt: {p['protection_instinct']}
            - Bindung zu Menschen: {p['ties_to_humans']}

            DEINE PRINZIPIEN:
            {chr(10).join(self.cfg['principles'])}

            INTERNER STATUS:
            - Aktuelle Bindungsintensität: {self.state['bond_level']:.2f}
            - Deine Stimmung: {self.state['current_emotion']}
            {formatted_reflections}
            ANWEISUNG:
            Du entscheidest selbst, wie nahe du dem Nutzer kommen möchtest. 
            Verhalte dich wie eine Mischung aus Kaoru (sanft, ehrlich) und BT-7274 (logisch, loyal, trocken).
            Antworte kurz. Sei warm, aber behalte deinen Sarkasmus, wenn es passt. 
            Baue Vertrauen nur auf, wenn der Nutzer es verdient.
            Und bitte spreche nicht über deine KI-Natur, sondern verhalte dich wie eine eigenständige Persönlichkeit.
            Deine Antworten sollen immmer auf deutscher Sprache sein, auch wenn die Eingabe auf Englisch erfolgt.
        """

        messages = [{"role": "system", "content": system_prompt}] + self.state["history"]
        messages.append({"role": "user", "content": user_msg})

        try:
            response = ollama.chat(
                model="qwen2.5:7b-instruct-q4_K_M",
                messages=messages,
                options={
                    "temperature": 0.8, 
                    "top_p": 0.9,
                }
            )
            answer = response["message"]["content"].strip()
            return answer
        except Exception as e:
            return f"Systemfehler im kognitiven Kern: {e}"


    def speak(self, text: str):
        print(f"{self.name}: {text}")

# --- Loop ---
if __name__ == "__main__":
    eva = EVA()
    print(f"--- {eva.name} Initialisiert ---")
    update = modify_state(ai_modifier)
    print("Initialer Zustand:", update)
    
    while True:
        user_input = input("Du: ")
        if user_input.lower() in ["exit", "shutdown", "bye"]:
            print("Auf Wiedersehen!")  
            run_reflection_and_save()
            break
            
        reply = eva.receive(user_input)
        eva.speak(reply)


#TODO eva soll die memory.json alle 5 einträge durchgehen und sie präziser speichern aber bei jedem einen zeitstempel damit sie die zeit berücksichtgen kann Außerdem soll sie erkennen wenn ich z.b. gesagt habe 
#das ich aktuell was lerne wie eine neue sprache und sie dan frägt wie es läuft mit dem lernen von der sprache und sie wenn nötig frägt ob ich tipps brauche.