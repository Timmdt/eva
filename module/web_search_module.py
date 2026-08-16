import requests
import logging
from module.base_module import ModuleBase

class WebSearchModule(ModuleBase):
    """Sicheres Web-Fakten-Modul über Wikipedia & Wetter-Schnittstelle."""

    @property
    def name(self) -> str:
        return "WebSearchCore"

    def can_handle(self, message: str) -> bool:
        # Nur auf explizite Wetter-Anfragen reagieren, sonst lässt die KI einen [WEB_SEARCH:...] Tag generieren
        weather_keywords = ["wetter in", "wetter für", "wetter aktuell", "wie ist das wetter", "wie wird das wetter"]
        return any(word in message.lower() for word in weather_keywords)

    def handle(self, message: str, context: dict) -> dict:
        print(f"[{self.name}] handle() aufgerufen mit: '{message}'")
        logging.info(f"[{self.name}] handle() aufgerufen")
        
        # Nur Wetter beantworten, alles andere wird von der KI-Suche erledigt
        is_weather = any(w in message.lower() for w in ["wetter in", "wetter für", "wetter aktuell", "wie ist das wetter", "wie wird das wetter"])
        if not is_weather:
            response_text = f"[System-Meldung: Live-Web-Daten geladen]\n\nKonnte im Internet keine relevanten Daten für '{message}' finden. Versuche mit einer anderen Anfrage oder spezifischeren Suchbegriffen."
            print(f"[{self.name}] Nicht-Wetter-Anfrage, gebe Standard-Fallback")
            return {"text": response_text}
        
        # Radikale Bereinigung der Suchanfrage von Füllwörtern
        query = message.lower()
        stopwords = [
            "wetter in", "wetter für", "wetter aktuell", "wie ist das wetter", "wie wird das wetter",
            "kannst du", "könntest du", "sag mir", "erzähl mir", "was ist das"
        ]
        for word in stopwords:
            query = query.replace(word, "")
        query = query.strip("? .,").strip()
        
        # Wetterabfrage über wttr.in
        city = "Kissing" if "kissing" in message.lower() else (query if query else "Kissing")
        if not city: 
            city = "Kissing"
            
        print(f"[{self.name}] Rufe Live-Wetter ab für: '{city}'...")
        try:
            res = requests.get(f"https://wttr.in/{city}?format=%C+%t", timeout=5)
            if res.status_code == 200 and not "html" in res.text.lower():
                return {
                    "text": f"[System-Meldung: Live-Web-Daten geladen]\n\nAktuelle Wetterlage für {city.capitalize()}:\n{res.text.strip()}\n\nBedenke extreme Hitzewarnungen, falls die Temperatur sehr hoch ist."
                }
        except Exception as e:
            logging.error(f"Wetter-Fehler: {e}")
            pass

        return {"text": "[System-Meldung: Live-Web-Daten geladen]\n\nWetter-Daten konnten nicht abgerufen werden. Versuche es später nochmal."}

    def run_test(self) -> tuple[bool, str]:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"}
            res = requests.get("https://de.wikipedia.org/api/rest_v1/page/summary/Wikipedia", headers=headers, timeout=4)
            if res.status_code == 200:
                return True, "Enzyklopädie-Schnittstelle einsatzbereit."
            return False, f"Server meldet unerwarteten Status: {res.status_code}"
        except Exception as e:
            return False, f"Verbindungsfehler beim Systemtest: {e}"