from __future__ import annotations

from datetime import datetime
from typing import Any

from .base_module import ModuleBase


class JarvisModule(ModuleBase):
    name = "JarvisCore"
    version = "0.1"
    description = "Basis-Jarvis-Modul für Zeit, Status und einfache EVA-Kommandos."

    triggers = ["zeit", "uhr", "wie spät", "status", "hilfe", "module"]

    def can_handle(self, message: str) -> bool:
        normalized = message.lower()
        return any(trigger in normalized for trigger in self.triggers)

    def handle(self, message: str, context: dict[str, Any]) -> dict[str, Any] | None:
        normalized = message.lower()
        if "zeit" in normalized or "uhr" in normalized or "wie spät" in normalized:
            now = datetime.now().strftime("%H:%M")
            return {"text": f"Es ist jetzt {now}. Ich bin bereit für den nächsten Schritt."}

        if "status" in normalized:
            bond = context.get("state", {}).get("bond_level", "unbekannt")
            emotion = context.get("state", {}).get("current_emotion", "neutral")
            return {
                "text": (
                    f"Aktueller Status: Bond-Level {bond:.2f}, Stimmung {emotion}. "
                    "Ich überwache deine Module und bin bereit."
                )
            }

        if "module" in normalized:
            module_list = context.get("module_names", [])
            if module_list:
                return {"text": f"Aktive Module: {', '.join(module_list)}."}
            return {"text": "Ich habe aktuell keine Module geladen."}

        if "hilfe" in normalized:
            return {
                "text": (
                    "Ich bin EVA. Du kannst mich nach der Zeit fragen, deinen Status abfragen oder "
                    "mir ein neues Modul geben. Sag einfach, was du brauchst."
                )
            }

        return None

    def run_test(self) -> tuple[bool, str]:
        sample = "Sag mir die Zeit"
        if not self.can_handle(sample):
            return False, "JarvisModule erkennt Zeit-Anfragen nicht."

        result = self.handle(
            sample,
            {
                "state": {"bond_level": 0.5, "current_emotion": "ruhig"},
                "module_names": ["JarvisCore"],
            },
        )
        text = result.get("text", "") if result else ""
        if "Es ist jetzt" not in text:
            return False, f"JarvisModule hat unerwartete Antwort: {text}"

        return True, "JarvisModule Test bestanden."
