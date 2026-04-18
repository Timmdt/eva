import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import ollama


STATE_PATH = Path("memory/state.json")
MEMORY_PATH = Path("memory/memory.json")


def _safe_json_load(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _atomic_json_write(data: dict, path: Path, prefix: str, suffix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=prefix, suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def load_memory(path: str | Path = MEMORY_PATH) -> dict:
    return _safe_json_load(Path(path))


def save_memory(memory: dict, path: str | Path = MEMORY_PATH) -> None:
    _atomic_json_write(memory, Path(path), "memory_", ".json")


def load_state(path: str | Path = STATE_PATH) -> dict:
    return _safe_json_load(Path(path))


def save_state(state: dict, path: str | Path = STATE_PATH) -> None:
    _atomic_json_write(state, Path(path), "state_", ".json")


def delete_state_history(path: str | Path = STATE_PATH) -> None:
    state = load_state(path)
    if state.pop("history", None) is not None:
        save_state(state, path)


def modify_state(modifier: Callable[[dict], dict], path: str | Path = STATE_PATH) -> dict:
    state = load_state(path)
    new_state = modifier(state) or state
    save_state(new_state, path)
    return new_state


def reflect(path: str | Path = STATE_PATH) -> str:
    state = load_state(path)
    bond_level = state.get("bond_level", "unbekannt")
    current_emotion = state.get("current_emotion", "unbekannt")

    system_prompt = f"""
        Du bist das Reflexions-Modul von EVA. Deine Aufgabe ist es, die folgende Konversation zusammenzufassen.
        Extrahiere die wichtigsten Informationen, Erkenntnisse und den allgemeinen Ton des Gesprächs.
        Fasse die Konversation in einem kurzen, prägnanten Text zusammen.

        Zusätzlicher Kontext:
        - Aktuelles Bindungslevel: {bond_level}
        - Aktuelle Emotion: {current_emotion}
        - Konversationshistorie: {state.get('history', [])}
        """

    history = [m for m in (state.get("history") or []) if m.get("role") == "user"]
    if len(history) > 50:
        history = history[-50:]

    messages = [{"role": "system", "content": system_prompt}] + history

    try:
        response = ollama.chat(
            model="qwen2.5:7b-instruct-q4_K_M",
            messages=messages,
            options={"temperature": 0.7, "top_p": 0.9},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return f"Systemfehler im kognitiven Kern: {e}"


def ai_modifier(state: dict) -> dict:
    state.setdefault("bond_level", 0.2)
    state["bond_level"] = min(1.0, state["bond_level"] + 0.01)
    history = state.setdefault("history", [])
    if len(history) > 20:
        del history[:-20]
    return state


def run_reflection_and_save() -> None:
    reflection_text = reflect()
    if not reflection_text or reflection_text.startswith("Systemfehler"):
        print("Reflexion fehlgeschlagen oder wurde übersprungen.")
        return

    memory_data = load_memory()
    timestamp = datetime.now(timezone.utc).isoformat()
    state = load_state()
    memory_data.setdefault("reflections", []).append(
        {
            "timestamp": timestamp,
            "bond_level": state.get("bond_level", "unbekannt"),
            "summary": reflection_text,
        }
    )
    save_memory(memory_data)
    delete_state_history()
    print("Reflexion wurde erfolgreich gespeichert.")



