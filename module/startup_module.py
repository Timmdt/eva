from __future__ import annotations

from typing import Any

from memory.memory_engine import load_memory

from .base_module import ModuleBase


class StartupModule(ModuleBase):
    name = "StartupAdvisor"
    version = "0.1"
    description = "Modul für den automatischen Start von EVA: Lernziele, Erinnerungen und langfristige Prioritäten."

    def can_handle(self, message: str) -> bool:
        return False

    def handle(self, message: str, context: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def on_start(self, context: dict[str, Any]) -> dict[str, Any] | None:
        memory = load_memory()
        learning_goals = memory.get("learning_goals", [])
        important_points = memory.get("important_points", [])
        projects = memory.get("projects", [])

        if not important_points and not projects and not learning_goals:
            return {
                "fallback_text": (
                    "Guten Start! Ich habe im Moment keine dringenden Erinnerungen oder Lernziele, "
                    "die ich dir nennen sollte. Sag mir einfach, was du als Nächstes angehen willst."
                )
            }

        return {
            "startup_memory": {
                "important_point": important_points[0] if important_points else None,
                "learning_goal": learning_goals[0] if learning_goals else None,
                "project": projects[0] if projects else None,
            }
        }

    def run_test(self) -> tuple[bool, str]:
        result = self.on_start({})
        if not result or not isinstance(result, dict):
            return False, "StartupModule liefert kein gültiges Ergebnis bei on_start."
        if "startup_memory" not in result and "fallback_text" not in result:
            return False, "StartupModule liefert weder startup_memory noch fallback_text."
        return True, "StartupModule Test bestanden."
