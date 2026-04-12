import json
import os
import tempfile
from typing import Callable
from datetime import datetime, timezone

import ollama

STATE_PATH = "memory/state.json"
MEMORY_PATH = "memory/memory.json"

def load_memory(path: str = MEMORY_PATH) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_memory(memory: dict, path: str = MEMORY_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix="memory_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=4)
        os.replace(tmp, path)  # atomarer Austausch
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)



def load_state(path: str = STATE_PATH) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_state(state: dict, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix="state_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        os.replace(tmp, path)  # atomarer Austausch
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def delete_state_history(path: str = STATE_PATH) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        state.pop("history", None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        pass

def modify_state(modifier: Callable[[dict], dict], path: str = STATE_PATH) -> dict:
    state = load_state(path)
    new_state = modifier(state) or state
    save_state(new_state, path)
    return new_state

def reflect(path: str = STATE_PATH) -> dict:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}


    bond_level = state.get('bond_level', 'unbekannt')
    current_emotion = state.get('current_emotion', 'unbekannt')

    system_prompt = f"""
        Du bist das Reflexions-Modul von EVA. Deine Aufgabe ist es, die folgende Konversation zusammenzufassen.
        Extrahiere die wichtigsten Informationen, Erkenntnisse und den allgemeinen Ton des Gesprächs.
        Fasse die Konversation in einem kurzen, prägnanten Text zusammen.

        Zusätzlicher Kontext:
        - Aktuelles Bindungslevel: {bond_level}
        - Aktuelle Emotion: {current_emotion}
        - Konversationshistorie: {state.get('history', [])}
        """

    history = [m for m in (state.get("history", []) or []) if m.get("role") == "user"]
    if history and len(history) > 50:
        # print(f"--- DEBUG: History (user-only) gekürzt von {len(history)} auf 50 Einträge ---")
        history = history[-50:]
    messages = [{"role": "system", "content": system_prompt}] + history

    # print("--- DEBUG: Messages an Ollama ---")
    # print(json.dumps(messages, indent=2, ensure_ascii=False))
    # print("---------------------------------")

    try:
        response = ollama.chat(
           
            model="qwen2.5:7b-instruct-q4_K_M",
            messages=messages,
            options={
                "temperature": 0.7,
                "top_p": 0.9,
            }
        )
        answer = response["message"]["content"].strip()
        # print("--- DEBUG: Antwort von Ollama ---", answer, "---")
        # print("--- DEBUG: Raw response ---", response)
        return answer
    except Exception as e:
        return f"Systemfehler im kognitiven Kern: {e}"

    


def ai_modifier(state: dict) -> dict:
    state.setdefault("bond_level", 0.2)
    state["bond_level"] = min(1.0, state["bond_level"] + 0.01)
    state.setdefault("history", [])
    if len(state["history"]) > 20:
        state["history"].pop(0)
    return state


def run_reflection_and_save():

    reflection_text = reflect()

    # Verbesserung: Nicht speichern, wenn die Reflexion fehlschlägt.
    if not reflection_text or reflection_text.startswith("Systemfehler"):
        print("Reflexion fehlgeschlagen oder wurde übersprungen.")
        return

    memory_data = load_memory()
    timestamp = datetime.now(timezone.utc).isoformat()

    # Die Reflexion als Objekt mit Zeitstempel speichern
    reflection_entry = {
        "timestamp": timestamp,
        "summary": reflection_text
    }

    if "reflections" not in memory_data:
        memory_data["reflections"] = []
    memory_data["reflections"].append(reflection_entry)

    save_memory(memory_data)
    delete_state_history()
    print("Reflexion wurde erfolgreich gespeichert.")



