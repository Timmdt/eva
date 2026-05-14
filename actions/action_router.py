from __future__ import annotations

from typing import Any, Callable


class ActionRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[str, dict[str, Any]], str]] = {}

    def register(self, action_name: str, handler: Callable[[str, dict[str, Any]], str]) -> None:
        self._handlers[action_name] = handler

    def dispatch(self, action_name: str, payload: str, context: dict[str, Any]) -> str:
        if action_name not in self._handlers:
            raise ValueError(f"Unbekannte Aktion: {action_name}")
        return self._handlers[action_name](payload, context)

    def available_actions(self) -> list[str]:
        return list(self._handlers.keys())
