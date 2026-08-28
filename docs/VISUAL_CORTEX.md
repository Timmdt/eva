# Desktop Agent und Presence Fusion

Der optionale `desktop_agent` läuft erst auf dem bereits geweckten normalen Desktop-PC. Er ergänzt die zentrale Raum-Presence des Sentry-PCs um Schreibtisch-Präsenz und besitzt absichtlich keine Wake-on-LAN- oder Shutdown-Funktion.

```bash
EVA_DESKTOP_AGENT_ENABLED=true python3 -m desktop_agent.main
```

Die Desktop-Webcam verarbeitet 1–5 Frames pro Sekunde. Face Detection läuft zuerst; lokale Identity Recognition nur bei erkanntem Gesicht. Zustandsänderungen und ein sparsamer Heartbeat werden per `POST /presence` an den EVA-Server gemeldet.

## Fusion

```text
room=true,  desk=false -> Nutzer im Raum, nicht am Arbeitsplatz
room=true,  desk=true  -> Nutzer am Arbeitsplatz
room=false, desk=false -> vermutlich abwesend
```

Persönlicher Memory-Kontext wird nur freigegeben, wenn eine registrierte Identity auch vom Desk-Sensor bestätigt ist. `UNKNOWN` und `Visitor` erhalten keinen privaten Kontext. Diese Identity dient ausschließlich Begrüßung, Profil- und Memory-Auswahl; sie ist kein Authentifizierungsfaktor für sensible Aktionen.

Gesichtsdeskriptoren werden bewusst und lokal in `data/faces.json` registriert. Frames werden standardmäßig nicht gespeichert. `EVA_PRESENCE_TOKEN` schützt den lokalen Presence-Endpunkt, wenn ein Token konfiguriert ist.

Die ältere `visual_cortex`-API bleibt für Kompatibilität erhalten; für die Drei-Rechner-Architektur ist `desktop_agent` der vorgesehene Einstiegspunkt.
