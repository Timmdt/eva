from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModuleBase(ABC):
    """Grundbaustein für EVA-Module.

    Jedes Modul kann Expertisen kapseln, sich selbst testen und Nachrichten verarbeiten.
    """

    name: str = "unnamed"
    version: str = "0.0"
    description: str = "Kein Modulbeschreibung vorhanden."

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self.context = context or {}

    @abstractmethod
    def can_handle(self, message: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def handle(self, message: str, context: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def run_test(self) -> tuple[bool, str]:
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }
