from __future__ import annotations

import logging

from memory.memory_engine import (
    load_memory,
    search_projects,
)


class EVAContextBuilder:
    """
    Lädt nur relevanten Kontext.

    Nicht:
        komplettes Memory -> LLM

    Sondern:
        Benutzerfrage
            ↓
        relevante Projekte
            ↓
        relevante Memoryinformationen
            ↓
        kleiner Kontext
    """

    def __init__(
        self,
        max_projects: int = 3,
        max_context_chars: int = 5000,
    ) -> None:
        self.max_projects = max_projects
        self.max_context_chars = max_context_chars

    def build(
        self,
        user_message: str,
    ) -> str:

        parts: list[str] = []

        project_context = self._build_project_context(
            user_message
        )

        if project_context:
            parts.append(
                project_context
            )

        reflection_context = (
            self._build_reflection_context()
        )

        if reflection_context:
            parts.append(
                reflection_context
            )

        context = "\n\n".join(
            parts
        ).strip()

        return context[
            : self.max_context_chars
        ]

    def _build_project_context(
        self,
        user_message: str,
    ) -> str:

        if not user_message.strip():
            return ""

        try:
            memory = load_memory()

            projects = search_projects(
                memory,
                user_message,
                fields=[
                    "name",
                    "keywords",
                    "dynamic_context.current_focus",
                    "dynamic_context.critical_fear",
                    "dynamic_context.knowledge_gaps",
                ],
            )

        except Exception as exc:
            logging.error(
                "[ContextBuilder] Projekt-Suche fehlgeschlagen: %s",
                exc,
            )
            return ""

        if not projects:
            return ""

        lines = [
            "RELEVANTE PROJEKT-DATEN:"
        ]

        for project in projects[
            : self.max_projects
        ]:

            name = project.get(
                "name",
                "unbekannt",
            )

            dynamic_context = (
                project.get(
                    "dynamic_context",
                    {},
                )
                or {}
            )

            current_focus = dynamic_context.get(
                "current_focus",
                "keine Angabe",
            )

            critical_fear = dynamic_context.get(
                "critical_fear",
                "keine Angabe",
            )

            knowledge_gaps = dynamic_context.get(
                "knowledge_gaps",
                [],
            )

            if not isinstance(
                knowledge_gaps,
                list,
            ):
                knowledge_gaps = []

            lines.append(
                f"- Projekt: {name}"
            )

            lines.append(
                f"  Fokus: {current_focus}"
            )

            if critical_fear != "keine Angabe":
                lines.append(
                    f"  Risiko: {critical_fear}"
                )

            if knowledge_gaps:
                lines.append(
                    "  Wissenslücken: "
                    + ", ".join(
                        str(value)
                        for value in knowledge_gaps[:5]
                    )
                )

        return "\n".join(lines)

    def _build_reflection_context(
        self,
    ) -> str:

        try:
            memory = load_memory()

        except Exception as exc:
            logging.error(
                "[ContextBuilder] Memory konnte nicht geladen werden: %s",
                exc,
            )
            return ""

        reflections = memory.get(
            "reflections",
            [],
        )

        if not isinstance(
            reflections,
            list,
        ):
            return ""

        recent = reflections[-3:]

        lines = [
            "LETZTE RELEVANTE REFLEXIONEN:"
        ]

        for reflection in recent:

            if not isinstance(
                reflection,
                dict,
            ):
                continue

            summary = reflection.get(
                "summary"
            )

            if summary:
                lines.append(
                    f"- {summary}"
                )

        if len(lines) == 1:
            return ""

        return "\n".join(lines)