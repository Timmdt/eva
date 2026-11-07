from __future__ import annotations

from typing import Any

from .base_module import ModuleBase


class SystemTestModule(ModuleBase):
    name = "SystemTestModule"
    version = "0.1"
    description = "Selbsttest-Modul für das EVA-System."

    def can_handle(self, message: str) -> bool:
        return "systemtest" in message.lower() or "modultest" in message.lower()

    def handle(self, message: str, context: dict[str, Any]) -> dict[str, Any] | None:
        if self.can_handle(message):
            return {"text": "Systemtest-Modul ist aktiv und funktionsfähig."}
        return None

    def run_test(self) -> tuple[bool, str]:
        sample_message = "Bitte führe einen Systemtest durch"
        can_handle = self.can_handle(sample_message)
        if not can_handle:
            return False, "SystemTestModule reagiert nicht auf Testanfragen."

        response = self.handle(sample_message, {})
        if not response or response.get("text") != "Systemtest-Modul ist aktiv und funktionsfähig.":
            return False, f"SystemTestModule unerwartete Antwort: {response}"

        return True, "SystemTestModule Test bestanden."
