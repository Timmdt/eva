# Desktop-PC mit dem EVA-Server verbinden

Die gesamte KI-Berechnung läuft auf dem **EVA-Server 192.168.2.15**.
Auf dem Windows-Haupt-PC läuft kein KI-Modell und kein Ollama-Dienst.
Die RTX 4060 des Haupt-PCs wird für die Modellberechnung nicht benötigt.

```text
Windows-Haupt-PC                       EVA-Server 192.168.2.15
EVA-Figur + Chat                       eva-companion.service (Benutzerdienst)
Monitoraufnahme als JPEG  ---------->  Token-Bridge :8766
                                      Ollama 127.0.0.1:11434
                                      Chat: qwen3:4b-instruct-2507-q4_K_M
                                      Bilder: qwen3-vl:2b-instruct-q4_K_M
Antwort / Bildschirmbeschreibung <---  Verarbeitung auf dem Server
```

Das bereits auf dem Server installierte Modell wurde über Ollamas `/api/show`
auf seine Vision-Fähigkeit geprüft. Ein Testbild mit grünem Rechteck wird über
die geschützte Bridge geschickt, um den vollständigen Weg zu prüfen.
Modellfamilie: [Qwen3-VL in Ollama](https://ollama.com/library/qwen3-vl).

Normale Unterhaltung und Rechenfragen verwenden das separate Gesprächsmodell.
Das Bildmodell erhält aktuelle Bilder bei ausdrücklichen Bildschirmfragen und
bei der eingeschalteten regelmäßigen Bildschirmbeobachtung. Screenshots werden
nicht als Kontext an jede normale Nachricht angehängt. Auch die Bridge verwirft
unpassende Bilder älterer Desktop-Versionen vor dem Modellaufruf.

## 1. Verbindungsdaten auf dem EVA-Server anzeigen

Im Projektordner `/home/kati/opt/eva`:

```bash
.venv/bin/python -m tools.setup_desktop_bridge --show-client
```

Das zeigt die Serveradresse und den privaten Bridge-Token ausschließlich in
deinem lokalen Terminal. Den Token nicht in Chats oder öffentliche Dateien kopieren.
Er liegt serverseitig in `.env` und ist in keinem Windows-Paket enthalten.

## 2. Im Windows-Agenten einstellen

Rechtsklick auf EVA → **Hauptmenü öffnen** → **Einstellungen**:

| Einstellung | Wert |
| --- | --- |
| KI-Backend | EVA-Bridge · Modell läuft auf dem Server |
| API-Adresse | `http://192.168.2.15:8766` |
| Bridge-Token | Wert aus dem Server-Terminal |
| Token merken | Optional im Windows-Anmeldeinformationstresor |
| Modellname | Wird serverseitig gewählt; Feld bei der Bridge deaktiviert |

**Einstellungen speichern**, dann im Chat eine Nachricht senden.
Es ist keine Ollama-Installation und kein Modelldownload auf dem Windows-PC nötig.

## 3. EVA den Bildschirm zeigen

Unter **Einstellungen** den gewünschten Monitor wählen. Dann im **Dashboard**
die **Bildschirmfreigabe** einschalten und **Was siehst du?** drücken.
Der Windows-Agent sendet ein aktuelles Bild an den Server; nur dort wird das
Bildmodell ausgeführt. Die Antwort erscheint im Chat.

Bei aktiver Freigabe werden außerdem in dem eingestellten Intervall kurze
Tätigkeitsbeschreibungen angefragt. Ausschalten stoppt neue Aufnahmen. Bilder
werden weder auf dem Windows-PC noch durch die Bridge als Dateien gespeichert.
Die Bildschirmfreigabe bleibt nach jedem Programmstart zunächst aus.

## Serverseitiger Dienst

Die Bridge läuft als Benutzer-Dienst des Benutzers `kati`:

```bash
systemctl --user status eva-companion.service
systemctl --user restart eva-companion.service
journalctl --user -u eva-companion.service -n 30 --no-pager
```

Der Dienst ist für den Benutzerstart aktiviert; für `kati` ist systemd-Linger
bereits eingeschaltet. Das eigentliche EVA-Hauptprogramm und der Benutzer-Dienst
sind getrennte Prozesse. Ollama läuft als vorhandener Systemdienst.

Die Konfiguration steht in `.env`:

```dotenv
EVA_COMPANION_HOST=192.168.2.15
EVA_COMPANION_PORT=8766
EVA_COMPANION_TOKEN=PRIVATE_ZUFAELLIGE_ZEICHENFOLGE
EVA_COMPANION_MODEL=qwen3-vl:2b-instruct-q4_K_M
EVA_COMPANION_CHAT_MODEL=qwen3:4b-instruct-2507-q4_K_M
EVA_COMPANION_OLLAMA_URL=http://127.0.0.1:11434
```

Die Installation lässt sich wiederholen, ohne den bestehenden Token oder andere
EVA-Einstellungen zu überschreiben:

```bash
.venv/bin/python -m tools.setup_desktop_bridge \
  --host 192.168.2.15 \
  --model qwen3-vl:2b-instruct-q4_K_M \
  --chat-model qwen3:4b-instruct-2507-q4_K_M \
  --install-user-service
```

Andere Modelle werden ausschließlich auf dem Server installiert: das Bildmodell
unter `EVA_COMPANION_MODEL`, das Gesprächsmodell unter `EVA_COMPANION_CHAT_MODEL`.
Danach die Bridge neu starten.
Das Setup installiert keine Modelle und prüft das ausgewählte Modell vorher.

## Wenn keine Verbindung zustande kommt

1. Serverdienst und Ollama prüfen.
2. In PowerShell auf Windows: `Test-NetConnection 192.168.2.15 -Port 8766`.
3. Bei einem geschlossenen Port prüfen, ob Server-Firewall/VLAN den Haupt-PC
   zulassen. Eine Router-Portweiterleitung ist dafür nicht erforderlich.
4. Bei „Zugriff verweigert“ den separaten Companion-Token erneut übertragen.
5. Bildfehler: gewählten Monitor, aktive Bildschirmfreigabe und Servermodell prüfen.

Die LAN-Verbindung verwendet HTTP. Für Verbindungen außerhalb des vertrauten
LAN ein privates VPN oder HTTPS verwenden; Ollama selbst muss nicht im LAN
veröffentlicht werden.

## Gesprächsqualität prüfen

Die kurze Live-Prüfung verwendet ausschließlich die gemeldeten Gesprächsfragen
und ein künstliches Testfenster, keine echten Desktop-Aufnahmen:

```bash
# Entwicklungsumgebung mit Pillow; die Windows-App benötigt Pillow nicht.
python3 -m tools.companion_dialog_eval
```

Der Bericht liegt lokal unter `data/benchmarks/desktop-dialog.json` und enthält
Antworten und Laufzeiten, keine Tokens oder Bildschirmbilder. Prüffälle: Smalltalk,
Nachfrage nach einer alten falschen Antwort, einfache Rechnung und sichtbarer
Fenstertitel/Status/Farbe. Diese wurden erfolgreich mit den echten Servermodellen
ausgeführt. Korrekte Antworten auf diese Fälle garantieren keine fehlerfreie
Bildinterpretation auf beliebigen Desktops; kleine oder unscharfe Schrift kann
weiterhin unlesbar sein.

Der Desktop nutzt weiterhin eigene Gespräche. EVAs zentraler Langzeitspeicher,
Stimme und Module sind über diese Bridge noch nicht angebunden. Sie transportiert
Chat und Screenshots zum serverseitigen Modell, keine Maus-/Tastatursteuerung.
