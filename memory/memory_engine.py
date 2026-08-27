import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import ollama
except ImportError:
    ollama = None


logger = logging.getLogger(__name__)

ROOT_PATH = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT_PATH / "memory" / "state.json"
MEMORY_PATH = ROOT_PATH / "memory" / "memory.json"

DEFAULT_MODEL = "mistral-nemo:12b-instruct-2407-q4_K_S"


# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------

def _safe_json_load(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        return data if isinstance(data, dict) else {}

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        logger.exception(
            "JSON-Datei konnte nicht geladen werden: %s",
            path,
        )
        return {}


def _atomic_json_write(
    data: dict,
    path: Path,
    prefix: str,
    suffix: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=prefix,
        suffix=suffix,
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                data,
                handle,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temp_path,
            path,
        )

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def load_memory(
    path: str | Path = MEMORY_PATH,
) -> dict:
    return _safe_json_load(Path(path))


def save_memory(
    memory: dict,
    path: str | Path = MEMORY_PATH,
) -> None:
    _atomic_json_write(
        memory,
        Path(path),
        "memory_",
        ".json",
    )


def load_state(
    path: str | Path = STATE_PATH,
) -> dict:
    return _safe_json_load(Path(path))


def save_state(
    state: dict,
    path: str | Path = STATE_PATH,
) -> None:
    _atomic_json_write(
        state,
        Path(path),
        "state_",
        ".json",
    )


# ---------------------------------------------------------------------------
# Generic search helpers
# ---------------------------------------------------------------------------

def _value_matches(
    value: Any,
    query: str,
) -> bool:
    query = query.lower().strip()

    if not query:
        return False

    if isinstance(value, str):
        return query in value.lower()

    if isinstance(value, list):
        return any(
            _value_matches(item, query)
            for item in value
        )

    if isinstance(value, dict):
        return any(
            _value_matches(item, query)
            for item in value.values()
        )

    return False


def _get_nested_value(
    data: dict,
    path: str,
) -> Any:
    current: Any = data

    for part in path.split("."):
        if not isinstance(current, dict):
            return None

        current = current.get(part)

    return current


def _priority_value(
    priority: str | None,
) -> int:
    if not isinstance(priority, str):
        return 0

    return {
        "hoch": 3,
        "mittel": 2,
        "niedrig": 1,
    }.get(
        priority.lower(),
        0,
    )


def _project_sort_key(
    project: dict,
) -> tuple[int, float]:
    priority = _priority_value(
        project.get("priority")
    )

    timestamp = 0.0

    for key in (
        "updated_at",
        "timestamp",
        "modified_at",
    ):
        raw = project.get(key)

        if not isinstance(raw, str):
            continue

        try:
            timestamp = datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            ).timestamp()
            break

        except ValueError:
            continue

    return (
        priority,
        timestamp,
    )


# ---------------------------------------------------------------------------
# History processing
# ---------------------------------------------------------------------------

def _clean_history(
    history: list[dict],
) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []

    for entry in history or []:
        if not isinstance(entry, dict):
            continue

        role = entry.get("role")
        content = entry.get("content")

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str):
            continue

        content = content.strip()

        if not content:
            continue

        cleaned.append(
            {
                "role": role,
                "content": content,
            }
        )

    return cleaned


def _history_pairs(
    history: list[dict],
    max_messages: int = 30,
) -> list[dict[str, str]]:
    cleaned = _clean_history(history)

    if max_messages <= 0:
        return []

    return cleaned[-max_messages:]


def _extract_sentences(
    text: str,
) -> list[str]:
    # Bewusst einfach gehalten, damit keine NLP-Bibliothek nötig ist.
    separators = (
        text.replace("?", ".")
        .replace("!", ".")
        .replace("\n", ".")
    )

    return [
        sentence.strip()
        for sentence in separators.split(".")
        if sentence.strip()
    ]


def _extract_learning_items(
    history: list[dict],
) -> list[str]:
    keywords = (
        "lernen",
        "lernen will",
        "möchte lernen",
        "will lernen",
        "ich will",
        "ich möchte",
        "ziel",
        "projekt",
        "interesse",
    )

    items: list[str] = []

    for entry in history:
        if entry.get("role") != "user":
            continue

        text = entry.get("content", "")
        lower = text.lower()

        if not any(
            keyword in lower
            for keyword in keywords
        ):
            continue

        for sentence in _extract_sentences(text):
            lower_sentence = sentence.lower()

            if (
                len(sentence) > 10
                and any(
                    keyword in lower_sentence
                    for keyword in keywords
                )
                and sentence not in items
            ):
                items.append(sentence)

    return items


def _extract_important_points(
    history: list[dict],
) -> list[str]:
    items: list[str] = []

    for entry in history:
        if entry.get("role") != "user":
            continue

        text = entry.get("content", "")

        for sentence in _extract_sentences(text):
            lower = sentence.lower()

            if (
                "sehr wichtig" in lower
                or "wichtig" in lower
                or "dringend" in lower
            ):
                if sentence not in items:
                    items.append(sentence)

    return items


# ---------------------------------------------------------------------------
# Chat memory
# ---------------------------------------------------------------------------

def save_chat_history(
    state: dict,
    path: str | Path = MEMORY_PATH,
) -> None:
    history = _clean_history(
        state.get("history", [])
    )

    if not history:
        return

    memory_data = load_memory(path)
    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    # Nur die aktuelle Gesprächseinheit speichern.
    memory_data.setdefault(
        "chat_logs",
        [],
    ).append(
        {
            "timestamp": timestamp,
            "history": history,
        }
    )

    learning_items = _extract_learning_items(
        history
    )
    important_points = _extract_important_points(
        history
    )

    if learning_items:
        goals = memory_data.setdefault(
            "learning_goals",
            [],
        )

        for item in learning_items:
            if item not in goals:
                goals.append(item)

    if important_points:
        points = memory_data.setdefault(
            "important_points",
            [],
        )

        for item in important_points:
            if item not in points:
                points.append(item)

    save_memory(
        memory_data,
        path,
    )


# ---------------------------------------------------------------------------
# Project parsing / merging
# ---------------------------------------------------------------------------

def _find_json_object(
    text: str,
) -> str | None:
    start = text.find("{")

    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index in range(
        start,
        len(text),
    ):
        char = text[index]

        if char == '"' and not escape:
            in_string = not in_string

        elif char == "\\" and not escape:
            escape = True
            continue

        elif not in_string:
            if char == "{":
                depth += 1

            elif char == "}":
                depth -= 1

                if depth == 0:
                    return text[
                        start : index + 1
                    ]

        escape = False

    return None


def _parse_project_result(
    raw: str,
) -> dict | None:
    json_text = _find_json_object(
        raw
    )

    if not json_text:
        return None

    try:
        parsed = json.loads(
            json_text
        )

        return parsed if isinstance(
            parsed,
            dict,
        ) else None

    except json.JSONDecodeError:
        return None


def _project_history_candidates(
    history: list[dict],
    max_messages: int = 30,
) -> list[dict]:
    return _history_pairs(
        history,
        max_messages=max_messages,
    )


def _merge_dicts(
    old: dict,
    new: dict,
) -> dict:
    """
    Rekursives Merge:
    Neue Informationen überschreiben alte Felder,
    fehlende alte Informationen bleiben erhalten.
    """
    result = dict(old)

    for key, value in new.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = _merge_dicts(
                result[key],
                value,
            )
        else:
            result[key] = value

    return result


def _store_project_result(
    project: dict,
    path: str | Path = MEMORY_PATH,
) -> None:
    if not isinstance(project, dict):
        return

    if project.get("created") is False:
        return

    project_name = str(
        project.get("name", "")
    ).strip()

    if not project_name:
        return

    memory_data = load_memory(path)
    projects = memory_data.setdefault(
        "projects",
        [],
    )

    old_project = next(
        (
            item
            for item in projects
            if str(
                item.get("name", "")
            ).strip().lower()
            == project_name.lower()
        ),
        None,
    )

    if old_project:
        merged = _merge_dicts(
            old_project,
            project,
        )
    else:
        merged = dict(project)

    merged["name"] = project_name
    merged.setdefault(
        "created_at",
        datetime.now(
            timezone.utc
        ).isoformat(),
    )
    merged["updated_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    # Projekt ersetzen, aber Reihenfolge erhalten.
    replaced = False
    new_projects: list[dict] = []

    for item in projects:
        if (
            str(
                item.get("name", "")
            ).strip().lower()
            == project_name.lower()
        ):
            new_projects.append(merged)
            replaced = True
        else:
            new_projects.append(item)

    if not replaced:
        new_projects.append(merged)

    memory_data["projects"] = sorted(
        new_projects,
        key=_project_sort_key,
        reverse=True,
    )

    save_memory(
        memory_data,
        path,
    )


def search_projects(
    memory: dict,
    query: str,
    fields: list[str] | None = None,
) -> list[dict]:
    """
    Lokale, schnelle Projektsuche.

    Keine KI-Anfrage nötig.
    """
    projects = memory.get(
        "projects",
        [],
    )

    if not query:
        return sorted(
            projects,
            key=_project_sort_key,
            reverse=True,
        )

    results: list[dict] = []

    query_lower = query.lower()

    for project in projects:
        search_fields = (
            fields
            if fields is not None
            else [
                "name",
                "keywords",
                "status",
                "dynamic_context",
            ]
        )

        for field in search_fields:
            value = _get_nested_value(
                project,
                field,
            )

            if _value_matches(
                value,
                query_lower,
            ):
                results.append(project)
                break

    return sorted(
        results,
        key=_project_sort_key,
        reverse=True,
    )


# ---------------------------------------------------------------------------
# State updates
# ---------------------------------------------------------------------------

def delete_state_history(
    path: str | Path = STATE_PATH,
) -> None:
    state = load_state(path)

    if state.pop(
        "history",
        None,
    ) is not None:
        save_state(
            state,
            path,
        )


def modify_state(
    modifier: Callable[[dict], dict],
    path: str | Path = STATE_PATH,
) -> dict:
    state = load_state(path)

    new_state = modifier(
        state
    ) or state

    save_state(
        new_state,
        path,
    )

    return new_state


def ai_modifier(
    state: dict,
) -> dict:
    state.setdefault(
        "bond_level",
        0.2,
    )

    try:
        bond = float(
            state["bond_level"]
        )
    except (TypeError, ValueError):
        bond = 0.2

    state["bond_level"] = min(
        1.0,
        bond + 0.01,
    )

    state.setdefault(
        "history",
        [],
    )

    state["history"] = _clean_history(
        state["history"]
    )

    # Im State darf der kurzfristige Verlauf begrenzt sein.
    # Der Langzeitverlauf liegt separat in memory.json.
    if len(state["history"]) > 20:
        state["history"] = state[
            "history"
        ][-20:]

    return state


# ---------------------------------------------------------------------------
# Reflection
# ---------------------------------------------------------------------------

REFLECTION_SYSTEM_PROMPT = """
Du bist das Reflexionsmodul von EVA.

Analysiere die bereitgestellte Unterhaltung.

Ziel:
- wichtigste Fakten erkennen
- wichtige Entscheidungen erkennen
- offene Punkte erkennen
- Lernziele erkennen
- Projektfortschritte erkennen
- den allgemeinen Gesprächston erkennen

Wichtig:
- erfinde nichts
- wiederhole nicht einfach die komplette Unterhaltung
- konzentriere dich auf Informationen, die langfristig nützlich sind
- persönliche Nebensächlichkeiten dürfen weggelassen werden

Antworte als kurze, sachliche Zusammenfassung.
"""


def reflect(
    path: str | Path = STATE_PATH,
    *,
    model: str = DEFAULT_MODEL,
    max_messages: int = 30,
) -> str:
    state = load_state(path)

    history = _project_history_candidates(
        state.get("history", []),
        max_messages=max_messages,
    )

    if not history:
        return ""

    if ollama is None:
        return (
            "Ollama ist nicht installiert. "
            "Reflexion ist nicht verfügbar."
        )

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": REFLECTION_SYSTEM_PROMPT.strip(),
                },
                *history,
            ],
            options={
                "temperature": 0.15,
                "top_p": 0.85,
            },
            stream=False,
            keep_alive=os.getenv("EVA_OLLAMA_KEEP_ALIVE", "30m"),
        )

        return str(
            response["message"]["content"]
        ).strip()

    except Exception:
        logger.exception(
            "Reflexion fehlgeschlagen."
        )
        return ""


# ---------------------------------------------------------------------------
# Project extraction
# ---------------------------------------------------------------------------

PROJECT_SYSTEM_PROMPT = """
Du bist das Projekt-Logbuch von EVA.

Prüfe die Unterhaltung auf ein langfristiges Projekt,
ein konkretes Vorhaben oder ein wichtiges Lernziel.

Wenn ein Projekt eindeutig erkennbar ist, antworte ausschließlich mit JSON:

{
  "created": true,
  "name": "kurzer Projekttitel",
  "status": "geplant|in Arbeit|pausiert|abgeschlossen",
  "priority": "hoch|mittel|niedrig",
  "keywords": ["..."],
  "dynamic_context": {
    "current_focus": "...",
    "critical_fear": "...",
    "knowledge_gaps": ["..."]
  }
}

Wenn kein ausreichend klares Projekt erkennbar ist:

{"created": false}

Wichtig:
- nichts erfinden
- vorhandene Fakten aus der Unterhaltung verwenden
- nicht künstlich ein Projekt aus einer normalen Frage machen
- nur ein Projektobjekt erzeugen, wenn genügend Informationen vorhanden sind
- reines JSON, kein Markdown
"""


def project_entry(
    path: str | Path = STATE_PATH,
    *,
    model: str = DEFAULT_MODEL,
    max_messages: int = 30,
) -> dict:
    state = load_state(path)

    history = _project_history_candidates(
        state.get("history", []),
        max_messages=max_messages,
    )

    if not history or ollama is None:
        return {
            "created": False
        }

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": PROJECT_SYSTEM_PROMPT.strip(),
                },
                *history,
            ],
            options={
                "temperature": 0.10,
                "top_p": 0.80,
            },
            stream=False,
            keep_alive=os.getenv("EVA_OLLAMA_KEEP_ALIVE", "30m"),
        )

        parsed = _parse_project_result(
            response["message"]["content"].strip()
        )

        if not parsed:
            return {
                "created": False
            }

        return parsed

    except Exception:
        logger.exception(
            "Projektanalyse fehlgeschlagen."
        )
        return {
            "created": False
        }


# ---------------------------------------------------------------------------
# Reflection pipeline
# ---------------------------------------------------------------------------

def run_reflection_and_save(
    *,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """
    Speichert die aktuelle Unterhaltung als Langzeitdaten,
    erstellt eine Reflexion und aktualisiert das Projekt-Memory.

    Rückgabe:
    {
        "history_saved": bool,
        "reflection_saved": bool,
        "project_saved": bool,
    }
    """
    state = load_state()

    if not state.get("history"):
        return {
            "history_saved": False,
            "reflection_saved": False,
            "project_saved": False,
        }

    # 1. Rohverlauf + automatisch erkannte Lernziele / wichtige Punkte.
    save_chat_history(state)

    result = {
        "history_saved": True,
        "reflection_saved": False,
        "project_saved": False,
    }

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    # 2. Reflexion
    reflection_text = reflect(
        model=model
    )

    if reflection_text:
        memory_data = load_memory()

        memory_data.setdefault(
            "reflections",
            [],
        ).append(
            {
                "timestamp": timestamp,
                "bond_level": state.get(
                    "bond_level",
                    "unbekannt",
                ),
                "summary": reflection_text,
            }
        )

        # Reflexionshistorie begrenzen.
        memory_data["reflections"] = (
            memory_data["reflections"][-100:]
        )

        save_memory(
            memory_data
        )

        result["reflection_saved"] = True

    # 3. Projektanalyse
    project_result = project_entry(
        model=model
    )

    if (
        isinstance(project_result, dict)
        and project_result.get("created") is not False
    ):
        _store_project_result(
            project_result
        )
        result["project_saved"] = True

    return result
