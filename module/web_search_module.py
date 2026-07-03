import requests
import logging
from module.base_module import ModuleBase

class WebSearchModule(ModuleBase):
    """Sicheres Web-Fakten-Modul über Wikipedia & Wetter-Schnittstelle."""

    @property
    def name(self) -> str:
        return "WebSearchCore"

    def can_handle(self, message: str) -> bool:
        trigger_words = ["suche nach", "google", "such nach", "daten von", "specs von", "was ist", "wetter in", "wetter für", "wetter aktuell"]
        return any(word in message.lower() for word in trigger_words)

    def handle(self, message: str, context: dict) -> dict:
        # Radikale Bereinigung der Suchanfrage von Füllwörtern
        query = message.lower()
        stopwords = [
            "google mal bitte nach der", "google nach", "google mal nach", 
            "suche nach", "such nach", "bitte nach", "kannst du mal nachschauen wie das",
            "wie ist das wetter in", "wie wird das wetter in", "wetter in", "wetter für", "was sind die daten von der"
        ]
        for word in stopwords:
            query = query.replace(word, "")
        query = query.strip("? .,").strip()

        # SPEZIALFALL: Wetterabfrage über wttr.in
        if "wetter" in message.lower() or "grad" in message.lower():
            city = "Kissing" if "kissing" in message.lower() else query
            if not city: city = "Kissing"
            print(f"[{self.name}] Rufe Live-Wetter ab für: '{city}'...")
            try:
                # Format "Format=v2" oder "format=%C+%t" liefert detailliertere Echtzeitwerte
                res = requests.get(f"https://wttr.in/{city}?format=%C+%t", timeout=5)
                if res.status_code == 200 and not "html" in res.text.lower():
                    return {
                        "text": f"[System-Meldung: Live-Web-Daten geladen]\n\nAktuelle Wetterlage für {city.capitalize()}:\n{res.text.strip()}\n\nBedenke extreme Hitzewarnungen, falls die Temperatur sehr hoch ist."
                    }
            except Exception:
                pass

        # STANDARD: Fakten-Suche über Wikipedia API
        print(f"[{self.name}] Rufe Wikipedia-Fakten ab für: '{query}'...")
        try:
            url = f"https://de.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(query)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
                "Accept": "application/json; charset=utf-8"
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                extract = data.get("extract", "")
                return {
                    "text": f"[System-Meldung: Live-Web-Daten geladen]\n\nFaktenbasis aus der Enzyklopädie:\n{extract}\n\nWarnung: Erfinde keine Details wie Getriebearten oder Rückwärtsgänge, wenn sie nicht im Text stehen!"
                }
            
            # Fallback: Freitext-Suche
            search_url = f"https://de.wikipedia.org/w/api.php?action=query&list=search&srsearch={requests.utils.quote(query)}&format=json"
            search_res = requests.get(search_url, headers=headers, timeout=5).json()
            search_results = search_res.get("query", {}).get("search", [])
            
            if search_results:
                snippets = [f"- {res['title']}: {res['snippet']}" for res in search_results[:2]]
                clean_text = "\n".join(snippets).replace('<span class="searchmatch">', '').replace('</span>', '')
                return {
                    "text": f"[System-Meldung: Live-Web-Daten geladen]\n\nMögliche Treffer:\n{clean_text}\n\nAnalysiere dies strikt ohne Halluzinationen."
                }

            return {"text": f"Keine direkten Einträge im Netz für '{query}' gefunden, Pilot."}

        except Exception as e:
            return {"text": f"Verbindung zum Netz fehlgeschlagen, Pilot: {e}"}

    def run_test(self) -> tuple[bool, str]:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"}
            res = requests.get("https://de.wikipedia.org/api/rest_v1/page/summary/Wikipedia", headers=headers, timeout=4)
            if res.status_code == 200:
                return True, "Enzyklopädie-Schnittstelle einsatzbereit."
            return False, f"Server meldet unerwarteten Status: {res.status_code}"
        except Exception as e:
            return False, f"Verbindungsfehler beim Systemtest: {e}"