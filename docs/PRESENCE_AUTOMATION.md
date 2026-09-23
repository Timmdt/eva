# Präsenz-Automation

Die optionale Präsenz-Automation reagiert ausschließlich auf bekannte
Raum-Identitäten, die über `POST /presence` gemeldet werden. Sie besitzt keine
Wake-on-LAN- oder Shutdown-Funktion.

## Verhalten

- Die erste bekannte Präsenz begrüßt den Nutzer einmalig.
- Innerhalb des Morgenfensters wird höchstens einmal täglich eine Begrüßung mit
  aktuellen Wetterdaten erzeugt.
- Eine Abwesenheit unterhalb von `EVA_PRESENCE_RETURN_BRIEFING_AFTER` bleibt
  vollständig still.
- Nach einer längeren Abwesenheit nennt EVA die ungefähre Dauer und fasst bis zu
  drei währenddessen erfasste Ereignisse zusammen.
- Unbekannte Gesichter lösen keine Begrüßung aus.
- Wiederholte Erkennungen werden durch Zustand und Cooldown entprellt.

Die Ausgabe läuft über `EVA.speak()`. Solange kein TTS-Ausgabegerät angebunden
ist, erscheint sie im EVA-Terminal. Der persistente Zustand liegt standardmäßig
in `data/presence_automation.json` und wird nicht versioniert.

## Konfiguration

```env
EVA_PRESENCE_AUTOMATION_ENABLED=true
EVA_PRESENCE_RETURN_BRIEFING_AFTER=900
EVA_PRESENCE_GREETING_COOLDOWN=14400
EVA_MORNING_GREETING_START=05:00
EVA_MORNING_GREETING_END=11:30
EVA_WEATHER_LOCATION=DEINE_STADT
EVA_PRESENCE_AUTOMATION_STATE_FILE=data/presence_automation.json
```

Alle Zeitangaben außer dem Morgenfenster sind Sekunden. Für die lokale Uhr wird
`EVA_TIMEZONE` verwendet.

## Sicherer manueller Test

EVA nach einer Konfigurationsänderung neu starten. Anschließend kann ein
bekannter Raum-Report ohne Sentry-Power-Control gesendet werden:

```bash
curl -X POST http://127.0.0.1:8765/presence \
  -H "Authorization: Bearer $EVA_PRESENCE_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"sensor":"room","presence":true,"identity":"Tim","confidence":0.95}'
```

Der aktuelle Automationsstatus ist danach unter `presence_automation` sichtbar:

```bash
curl http://127.0.0.1:8765/health
```

Für einen Abwesenheitstest zunächst `presence:false` senden. Mit einem temporär
kleinen Wert wie `EVA_PRESENCE_RETURN_BRIEFING_AFTER=10` kann die Rückkehr nach
zehn Sekunden geprüft werden. Danach den Wert wieder auf `900` setzen.

Spätere Home-Assistant- oder EVA-Integrationen können relevante Meldungen über
`PresenceAutomation.record_event()` für das nächste Rückkehr-Briefing erfassen.
