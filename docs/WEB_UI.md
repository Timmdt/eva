# EVA-Weboberfläche

Die Weboberfläche läuft im vorhandenen EVA-HTTP-Server und verwendet dieselbe
EVA-Instanz wie das Terminal. Antworten werden live angezeigt. Sobald die
lokale Spracherzeugung fertig ist, lädt der Browser die zugehörige Audiodatei
und spielt sie ab. Dafür ist weder ein Cloud-Dienst noch ein Lautsprecher an
der EVA-VM nötig.

## Start

1. EVA nach einer Konfigurationsänderung neu starten.
2. Auf einem Rechner im selben Netzwerk diese Adresse öffnen:

   ```text
   http://192.168.2.15:8765/
   ```

3. Den Web-Token anzeigen und in den Anmeldedialog kopieren:

   ```bash
   cd ~/opt/eva
   grep '^EVA_WEB_TOKEN=' .env
   ```

Der Token wird nur lokal im Browser gespeichert. Er ist unabhängig vom
Presence- und Shutdown-Token und sollte nicht weitergegeben werden.

## Sprechen im Browser

`EVA_TTS_ENABLED=true` aktiviert EVAs Stimme. Für Browser-Audio muss
`EVA_TTS_OUTPUT_FILE` auf eine MP3- oder WAV-Datei zeigen, zum Beispiel:

```dotenv
EVA_TTS_OUTPUT_FILE=data/tts/eva-xtts.mp3
```

Mit dem Schalter **Stimme automatisch abspielen** kann die automatische
Wiedergabe deaktiviert werden. Falls der Browser Autoplay blockiert, erscheint
unter EVAs Antwort ein Play-Knopf.

## Einstellungen

| Variable | Bedeutung |
| --- | --- |
| `EVA_WEB_ENABLED` | Schaltet Oberfläche und Web-API ein. |
| `EVA_WEB_TOKEN` | Geheimer Zugriffstoken für Chat, Verlauf und Audio. |
| `EVA_WEB_MAX_MESSAGE_CHARS` | Maximale Länge einer Nachricht. |
| `EVA_WEB_HISTORY_MESSAGES` | Anzahl geladener Verlaufseinträge. |
| `EVA_WEB_AUDIO_DIR` | Temporärer Ordner für Browser-Audio. |
| `EVA_WEB_AUDIO_RETENTION` | Anzahl der behaltenen Audiodateien. |
| `EVA_WEB_VOICE_TIMEOUT` | Maximale Wartezeit auf die lokale TTS-Ausgabe. |

## Sicherheit

Port 8765 sollte in der Firewall ausschließlich für vertrauenswürdige Geräte
im lokalen Netz freigegeben sein. Die HTML-Oberfläche ist öffentlich abrufbar,
aber Status, Verlauf, Chat und Audio funktionieren nur mit dem Web-Token.
Nachrichten und Audiodateien bleiben zwischen deinem EVA-Server und deinem
Browser; sie werden an keinen Cloud-Dienst gesendet.
