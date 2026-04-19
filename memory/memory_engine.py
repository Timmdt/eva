import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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


def _value_matches(value: Any, query: str) -> bool:
    if isinstance(value, str):
        return query.lower() in value.lower()
    if isinstance(value, list):
        return any(_value_matches(item, query) for item in value)
    if isinstance(value, dict):
        return any(_value_matches(item, query) for item in value.values())
    return False


def _get_nested_value(data: dict, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _priority_value(priority: str | None) -> int:
    if not isinstance(priority, str):
        return 0
    rank = {"hoch": 3, "mittel": 2, "niedrig": 1}
    return rank.get(priority.lower(), 0)


def _parse_date(value: Any) -> float:
    if isinstance(value, str):
        for key in ["updated_at", "timestamp", "modified_at"]:
            if key in value:
                try:
                    return datetime.fromisoformat(value).timestamp()
                except ValueError:
                    continue
    return 0.0


def _project_sort_key(project: dict) -> tuple[int, float]:
    priority = _priority_value(project.get("priority"))
    timestamp = 0.0
    for key in ("updated_at", "timestamp", "modified_at"):
        if key in project:
            try:
                timestamp = datetime.fromisoformat(project[key]).timestamp()
                break
            except (ValueError, TypeError):
                continue
    return (priority, timestamp)


def search_projects(memory: dict, query: str, fields: list[str] | None = None) -> list[dict]:
    """Suche Projekte in memory.json nach name, keywords oder Kontext."""
    projects = memory.get("projects", [])
    if not query:
        return sorted(projects, key=_project_sort_key, reverse=True)

    results: list[dict] = []
    for project in projects:
        if fields is None:
            if _value_matches(project, query):
                results.append(project)
                continue

        for field in fields or []:
            value = _get_nested_value(project, field)
            if _value_matches(value, query):
                results.append(project)
                break

    return sorted(results, key=_project_sort_key, reverse=True)


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
        return f"Systemfehler im reflect Kern: {e}"


def project_entry(path: str | Path = STATE_PATH) -> str:
    state = load_state(path)
    system_prompt = f"""
        Du bist das Projekt-Logbuch von EVA. Deine Aufgabe ist es, aus dem vorhandenen dynamic_context ein vollständiges Projektobjekt zu erzeugen.
        Du bekommst nur dynamic_context als verlässliche Projektinformation. Erstelle daraus zusätzlich sinnvoll:
        - name: ein kurzer Projekt-Titel
        - status: der aktuelle Status (z.B. "in progress", "abgeschlossen", "geplant")
        - priority: Priorität des Projekts (z.B. "hoch", "mittel", "niedrig")
        - keywords: wichtige Stichwörter zum Projekt
        - dynamic_context: die vorhandenen Kontextdaten

        Verwende den dynamic_context als Ausgangspunkt und ergänze fehlende Projektfelder selbst.
        Gib das Ergebnis als gültiges JSON-Objekt zurück.
        """
    
    # TODO time stamps müssen unten gebaut werden um die richtige zeit zu erfassen
    
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
        return f"Systemfehler im project_entry Kern: {e}"

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

    print(project_entry())
    delete_state_history()
    print("Reflexion wurde erfolgreich gespeichert.")


# def run_logbook_entry() -> None:

