import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import ollama
except ImportError:
    ollama = None

ROOT_PATH = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_PATH / "memory" / "state.json"
MEMORY_PATH = ROOT_PATH / "memory" / "memory.json"


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


def _extract_learning_items(history: list[dict]) -> list[str]:
    keywords = ["lernen", "lernen will", "möchte lernen", "will lernen", "ich will", "ich möchte", "ziel", "projekt", "interesse"]
    items: list[str] = []
    for entry in history:
        if entry.get("role") != "user":
            continue
        text = entry.get("content", "")
        lower = text.lower()
        if any(keyword in lower for keyword in keywords):
            sentences = [s.strip() for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
            for sentence in sentences:
                if any(keyword in sentence.lower() for keyword in keywords) and len(sentence) > 10:
                    if sentence not in items:
                        items.append(sentence)
    return items


def _extract_important_points(history: list[dict]) -> list[str]:
    items: list[str] = []
    for entry in history:
        if entry.get("role") != "user":
            continue
        text = entry.get("content", "")
        lower = text.lower()
        if "wichtig" in lower or "sehr wichtig" in lower or "dringend" in lower:
            sentences = [s.strip() for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
            for sentence in sentences:
                if "wichtig" in sentence.lower() or "dringend" in sentence.lower():
                    if sentence not in items:
                        items.append(sentence)
    return items


def save_chat_history(state: dict, path: str | Path = MEMORY_PATH) -> None:
    memory_data = load_memory(path)
    history = state.get("history", [])
    if not history:
        return

    timestamp = datetime.now(timezone.utc).isoformat()
    memory_data.setdefault("chat_logs", []).append(
        {
            "timestamp": timestamp,
            "history": history,
        }
    )

    learning_items = _extract_learning_items(history)
    important_points = _extract_important_points(history)

    if learning_items:
        memory_data.setdefault("learning_goals", [])
        for item in learning_items:
            if item not in memory_data["learning_goals"]:
                memory_data["learning_goals"].append(item)

    if important_points:
        memory_data.setdefault("important_points", [])
        for item in important_points:
            if item not in memory_data["important_points"]:
                memory_data["important_points"].append(item)

    save_memory(memory_data, path)


def _find_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if char == "\"" and not escape:
            in_string = not in_string
        elif char == "\\" and not escape:
            escape = True
            continue
        elif char == "{" and not in_string:
            depth += 1
        elif char == "}" and not in_string:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
        escape = False
    return None


def _parse_project_result(raw: str) -> dict | None:
    json_text = _find_json_object(raw)
    if not json_text:
        return None
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None


def _project_history_candidates(history: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for entry in history:
        if entry.get("role") not in {"user", "assistant"}:
            continue
        if not isinstance(entry.get("content"), str):
            continue
        candidates.append(entry)
    return candidates[-50:]


def _store_project_result(project: dict, path: str | Path = MEMORY_PATH) -> None:
    if not project or not isinstance(project, dict):
        return

    memory_data = load_memory(path)
    memory_data.setdefault("projects", [])

    project_name = project.get("name")
    if project_name:
        memory_data["projects"] = [
            item for item in memory_data["projects"] if item.get("name") != project_name
        ]

    memory_data["projects"].append(project)
    save_memory(memory_data, path)


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

    if ollama is None:
        return "Ollama ist nicht installiert. Reflexion ist zurzeit nicht verfügbar."

    try:
        response = ollama.chat(
            model="mistral-nemo:12b-instruct-2407-q4_K_S",
            messages=messages,
            options={"temperature": 0.2, "top_p": 0.9},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return f"Systemfehler im reflect Kern: {e}"


def project_entry(path: str | Path = STATE_PATH) -> dict:
    state = load_state(path)
    system_prompt = """
        Du bist das Projekt-Logbuch von EVA. Deine Aufgabe ist es, aus der vorliegenden Konversation ein Projektobjekt zu erzeugen, wenn ein langfristiges Ziel, ein wichtiges Lernvorhaben oder ein klares Projekt erkennbar ist.
        Du kannst vorhandenen dynamic_context nutzen, falls er im Speicher existiert. Wenn dynamic_context nicht vorhanden ist, arbeite allein mit der vollständigen Gesprächshistorie.
        Verwende keine festen Schlüsselwortlisten. Analysiere stattdessen den Kontext und finde projektbezogene Informationen, selbst wenn sie nicht explizit als "Projekt" bezeichnet sind.
        Erstelle sinnvoll:
        - name: ein kurzer Projekt-Titel
        - status: der aktuelle Status (z.B. "in progress", "abgeschlossen", "geplant")
        - priority: Priorität des Projekts (z.B. "hoch", "mittel", "niedrig")
        - keywords: wichtige Stichwörter zum Projekt
        - dynamic_context: die vorhandenen Kontextdaten

        Wenn keine ausreichenden Informationen vorliegen oder die aktuellen Nachrichten keinen Projektbezug haben, antworte exakt mit: {"created": false}
        Gib nur reines JSON zurück. Verwende keine Codeblöcke, keine Erklärung und keine zusätzlichen Textteile.
        """
    
    history = _project_history_candidates(state.get("history") or [])
    if not history:
        return {"created": False}

    messages = [{"role": "system", "content": system_prompt}] + history

    if ollama is None:
        return {"created": False}

    try:
        response = ollama.chat(
            model="mistral-nemo:12b-instruct-2407-q4_K_S",
            messages=messages,
            options={"temperature": 0.2, "top_p": 0.9},
        )
        parsed = _parse_project_result(response["message"]["content"].strip())
        if not parsed:
            return {"created": False}
        return parsed
    except Exception:
        return {"created": False}

def ai_modifier(state: dict) -> dict:
    state.setdefault("bond_level", 0.2)
    state["bond_level"] = min(1.0, state["bond_level"] + 0.01)
    history = state.setdefault("history", [])
    if len(history) > 20:
        del history[:-20]
    return state


def run_reflection_and_save() -> None:
    state = load_state()
    save_chat_history(state)

    reflection_text = reflect()
    memory_data = load_memory()
    timestamp = datetime.now(timezone.utc).isoformat()

    if reflection_text and not reflection_text.startswith("Systemfehler"):
        memory_data.setdefault("reflections", []).append(
            {
                "timestamp": timestamp,
                "bond_level": state.get("bond_level", "unbekannt"),
                "summary": reflection_text,
            }
        )
        save_memory(memory_data)
    else:
        print("Reflexion fehlgeschlagen oder wurde übersprungen.")

    project_result = project_entry()
    if project_result:
        memory_data = load_memory()
        memory_data.setdefault("project_entries", []).append(
            {
                "timestamp": timestamp,
                "project_entry": project_result,
            }
        )
        save_memory(memory_data)

        if project_result.get("created") is not False:
            _store_project_result(project_result)

    print("Reflexion wurde erfolgreich gespeichert.")


# def run_logbook_entry() -> None:

