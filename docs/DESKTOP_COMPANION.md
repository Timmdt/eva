# EVA Desktop Agent · Gothic Edition

Eine native Desktop-Anwendung für Windows 10 und 11. EVA verwendet den weiblichen
Gothic-Anime-Charakter aus deinem Character Sheet. Sie sitzt als transparente,
rahmenlose Figur an der tatsächlichen Taskleistenkante. Die Position ist gesperrt.
Ein Linksklick öffnet den kleinen Chat; ein Rechtsklick das Short Menu.

**Für deinen Aufbau:** Auf dem Haupt-PC soll kein KI-Modell laufen. Verwende
die EVA-Bridge auf `http://192.168.2.15:8766`; Text- und Bildmodell laufen auf
dem EVA-Server. Die eingerichtete Verbindung und die Schritte im Desktop-Agenten
stehen in [DESKTOP_SERVER_LINK.md](DESKTOP_SERVER_LINK.md).

## Start auf deinem Windows-Haupt-PC

1. `dist/EVA-Windows.zip` auf den Haupt-PC kopieren und vollständig entpacken.
2. Python **3.11 oder neuer**, einschließlich Python Launcher (`py`), installieren.
3. Im Ordner `EVA` auf **start_eva_desktop.cmd** doppelklicken. Der erste Start
   erstellt `.venv-eva-desktop` und installiert Qt; dazu ist einmalig Internet nötig.
4. EVA erscheint an der Taskleiste. Eine KI-Verbindung ist für den Start nicht nötig.
5. Rechtsklick → **Hauptmenü öffnen** → **Einstellungen** für Monitor, Größe und KI.

Bei Problemen `start_eva_desktop_debug.cmd` starten; dort bleiben Fehlermeldungen
sichtbar. Im Quellprojekt kann die App alternativ so gestartet werden:

```powershell
py -3 -m venv .venv-eva-desktop
.venv-eva-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
.venv-eva-desktop\Scripts\pythonw.exe -m desktop_agent.companion
```

Der Haupt-PC benötigt keinen EVA-Kern, keine Datenbank und keine Webcam-Pakete.
Die Oberfläche startet ausschließlich die Figur, kein gewöhnliches Hauptfenster.
Die bestehende Webcam-Präsenzfunktion `desktop_agent.main` bleibt unabhängig.

### Optional: Windows-EXE bauen

`build_eva_exe.cmd` baut auf Windows mit PyInstaller eine Version unter
`dist/EVA Desktop Agent/EVA Desktop Agent.exe`. Den **gesamten Ordner** verteilen,
einschließlich `_internal`; die EXE benötigt dann keine separate Python-Installation.
Die Build-Vorlage liegt unter `deployment/eva_desktop.spec` und nimmt die Gothic-
Assets mit auf. Der Windows-EXE-Build wurde auf dem Linux-Entwicklungsrechner
nicht ausgeführt oder geprüft. Das ausgelieferte ZIP ist das startbare Python-Paket.

## Bedienung

- **Linksklick auf die sichtbare Figur:** kleiner Chat neben EVA, Zustand Zuhören.
- **Enter:** Nachricht senden. **Escape / ×:** kleinen Chat schließen.
- **Rechtsklick:** Chat öffnen, Hauptmenü öffnen, Pose wechseln, EVA verstecken,
  EVA beenden. Das Popup schließt beim Klick außerhalb.
- **Position ändern:** im Hauptmenü über Monitor und Position auf der Taskleistenkante.
  Ziehen mit der Maus bewegt EVA nicht.
- **Feinabgleich zur Kante:** Einstellungen → **Taskleisten-Feinabgleich**.
  Standard ist 0 Pixel; positive Werte verschieben EVA nach unten, negative nach
  oben. Falls nötig zunächst mit 1–3 Pixeln an die sichtbare Windows-Kante anpassen.
- **Verstecken:** Figur verschwindet, der Prozess und das Tray-Symbol bleiben aktiv.
- **Tray:** EVA anzeigen, Chat/Hauptmenü öffnen, Freigabe ausschalten, vollständig beenden.
- **Fenster schließen:** versteckt Chat oder Hauptmenü. **EVA beenden** stoppt Timer,
  bricht laufende HTTP-Anfragen ab und schließt sämtliche Fenster und das Tray.
- Auf Systemen ohne Tray-Unterstützung wird beim Verstecken das Hauptmenü als
  erreichbarer Rückweg geöffnet. Das ist vor allem für Linux-Entwicklung relevant.

## Hauptmenü

| Bereich | Inhalt |
| --- | --- |
| Dashboard | Agentenstatus, aktuelle Pose, KI-Backend, Monitor/Taskleistenkante, Bildschirmfreigabe |
| Chat | Großer Chatbereich, lokale Unterhaltungen wechseln, neue Gespräche, Gespräch löschen |
| Charakter | Posen, acht Ausdrucksporträts, ehrlicher Status der vorhandenen Frames |
| Outfits | Gothic-Standard, validierte externe JSON-Outfits laden |
| Einstellungen | Windows-Autostart, Topmost, Größe, Deckkraft, Position, Monitor, Animationen, Müdigkeit, KI und Sprache |

Die Oberfläche ist deutsch; die gespeicherte Spracheinstellung ist für weitere
Übersetzungen vorbereitet. In dieser Version wird ausschließlich Deutsch angeboten.
Die Ausdrucksauswahl zeigt Porträts. Sie verformt das Gesicht der Ganzkörperpose nicht.

## Charakter und Posen

Die Assets liegen unter `assets/character/poses/` und `expressions/`, das Manifest
unter `assets/character/outfits/gothic.json`. Die Anwendung verwendet diese Gothic-
Assets und keine der früheren Roboter-, Cyberpunk- oder anderen Entwurfsfiguren.

Es gibt zehn unterschiedliche Original-Körperposen aus der bereitgestellten
`eva.zip`, acht bisherige Ausdrucksporträts und 17 Zustandszuordnungen mit
ausdrücklich gekennzeichneten statischen Ersatzposen.
Alle gelieferten Posen sind **statische Einzelbilder**. Es gibt noch keine echten
Blink-, Atem-, Haar- oder Mundbewegungsframes. Talking verwendet Listening;
Annoyed verwendet Idle mit Hinweis auf das separate Ausdrucksporträt.

Der Animationsschalter spielt ausschließlich echte zusätzliche PNG-Frames ab,
sobald ein Outfit diese bereitstellt. Die App simuliert keine Gesichtsmorphs oder
Lippensynchronisation. Müdigkeit und Schlafen wechseln zu den entsprechenden
vorhandenen Standbildern. Unter Windows wird dafür die systemweite Inaktivität
über `GetLastInputInfo` verwendet, ohne Tastatureingaben aufzuzeichnen.

Jede Pose definiert Skalierung und einen normalisierten Anker. Sitzende Bilder
richten den unteren Sitz-/Bodenkontakt an der Taskleistenkante aus, stehende Bilder
werden größer skaliert und auf den verfügbaren Monitor begrenzt. Schlafende Bilder
sind kompakter. Der horizontale Anker bleibt bei Zustandswechseln stabil.

Die Standardpose sitzt mit verschränkten Beinen und vollständig sichtbaren
Schuhen. Auch die neue Knie-hoch-Pose zum Zuhören/Nachdenken zeigt die Schuhe
vollständig. Sämtliche Körperbilder werden bytegleich mit den PNGs aus `eva.zip`
verwendet, einschließlich Transparenz. Kontaktanker werden aus dem sichtbaren
Sitz-/Fußbereich ermittelt; der standardmäßige Gothic-Pfad bleibt bei Updates
relativ zum aktuellen Paket.

Die Körperposen haben nun die Auflösung der gelieferten Einzelbilder statt
kleiner Ausschnitte aus dem früheren Atlas. Nur die acht Ausdrucksporträts
stammen weiterhin aus der früheren Freistellung des Character Sheets.
Vollständige Herkunft, Dateizuordnungen, fehlende Frames und Qualitätshinweise:
[ASSET_LIMITS.md](../assets/character/ASSET_LIMITS.md).

## KI: offline, Ollama oder EVA-Bridge

Ohne konfigurierte KI bleibt EVA vollständig bedienbar. Beim Senden zeigt sie
verständlich, wo die Verbindung eingerichtet werden kann. Es werden weder
API-Schlüssel eingebaut noch automatisch Modelle installiert.

### Ollama direkt

Ollama kann auf dem Windows-PC oder einem vertrauenswürdigen anderen Rechner
laufen. In den Einstellungen **Ollama direkt**, eine Basisadresse ohne API-Pfad
und einen installierten Modellnamen wählen. Beispiel:

```text
API-Adresse: http://127.0.0.1:11434
Modell: qwen3-vl:4b-instruct
```

Das multimodale Modell ist für die optionale Bildschirmansicht geeignet. Mit
anderen Textmodellen funktioniert Chat; sie müssen Bilder nicht unterstützen.
Die RTX 4060 des Haupt-PCs wird nur benutzt, wenn Ollama dort tatsächlich läuft.
Die reale Geschwindigkeit und der VRAM-Verbrauch wurden hier nicht gemessen.
Modellquelle: [Ollama Qwen3-VL](https://ollama.com/library/qwen3-vl:4b-instruct).
Chat-Protokoll: [Ollama API](https://docs.ollama.com/api/chat).

### EVA-Bridge auf dem EVA-Rechner

Die vorhandene separate Bridge bleibt nutzbar. Auf dem EVA-Rechner das Modell
installieren und einen eigenen zufälligen Token erzeugen:

```bash
ollama pull qwen3-vl:2b-instruct-q4_K_M
ollama pull qwen3:4b-instruct-2507-q4_K_M
python3 -c "import secrets; print(secrets.token_hex(32))"
```

In `.env` auf diesem Rechner ergänzen, Platzhalter ersetzen:

```dotenv
EVA_COMPANION_HOST=0.0.0.0
EVA_COMPANION_PORT=8766
EVA_COMPANION_TOKEN=HIER_DEN_NEU_ERZEUGTEN_TOKEN_EINTRAGEN
EVA_COMPANION_MODEL=qwen3-vl:2b-instruct-q4_K_M
EVA_COMPANION_CHAT_MODEL=qwen3:4b-instruct-2507-q4_K_M
EVA_COMPANION_OLLAMA_URL=http://127.0.0.1:11434
```

```bash
.venv/bin/python -m desktop_agent.companion_server
```

Im Windows-Agenten **EVA-Bridge** wählen, etwa `http://192.168.2.15:8766`
und den separaten Token eintragen. Bei diesem Backend bestimmt die Bridge das
Modell. Der Modellname im Desktop gilt für direkte Ollama-Verbindungen.
Die systemd-Vorlage liegt in `deployment/systemd/eva-companion.service`.
Nach Änderungen am Bridge-Systemprompt die Bridge neu starten.

Ports nur im vertrauenswürdigen LAN/VPN freigeben. HTTP ist unverschlüsselt;
für andere Netze HTTPS oder ein privates VPN verwenden. Ollama kann bei Nutzung
auf demselben Rechner an Loopback gebunden bleiben. Keine Router-Portfreigaben.

Das Chat-Backend ist austauschbar (`app/ai.py`, Backend-Schnittstelle und Registry).
HTTP-Streaming läuft in einem separaten Thread, mit Verbindungszeitlimit,
Abbruchfunktion und sauberem Socket-Shutdown. Ein Fehler blockiert die Oberfläche
nicht. Zustände wechseln Thinking → Talking → Listening.

EVAs zentraler Langzeitspeicher, Stimme und sonstige EVA-Module sind hier noch
nicht angebunden; der Desktop besitzt eigene lokale Gespräche. Computersteuerung
über Maus oder Tastatur ist nicht implementiert.

## Optionale Bildschirmfreigabe

Im Dashboard einschalten; sie ist bei jedem Programmstart aus und wird beim
Monitorwechsel oder Anschluss/Entfernen eines Monitors ausgeschaltet.
Bei ausdrücklich bildschirmbezogenen Chatnachrichten wird ein frischer Screenshot
des gewählten Monitors gesendet. Smalltalk, Rechenfragen und sonstige normale
Unterhaltung benötigen keine Aufnahme. Das gilt zusätzlich serverseitig für
ältere Desktop-Versionen, die noch zu jeder Nachricht ein Bild übertragen.
Zusätzlich ist eine regelmäßige kurze Tätigkeitsbeschreibung möglich, mit dem
Intervall aus den Einstellungen (30–300 Sekunden). Ohne Vision-Modell kann die
KI Bilder ablehnen. Es wird kein Video aufgenommen.

Unter **Einstellungen → EVA und Chat in Screenshots anzeigen** legst du fest,
ob die eigenen Fenster mit aufgenommen werden. Die Option ist standardmäßig
**eingeschaltet**. EVA und Chat bleiben dann auch bei KI-Aufnahmen sichtbar.
Für normale Windows-Screenshots `Windows + Umschalt + S` drücken und einen
Bildschirmausschnitt wählen, der Figur und Chat enthält. Das Hauptmenü kann
vorher geschlossen werden; die Figur und der kleine Chat bleiben separat offen.

Wenn du die Option ausschaltest, werden die eigenen Fenster unter Windows nach
Möglichkeit aus Bildschirmaufnahmen ausgeschlossen. Das betrifft auch Snipping
Tool und Bildschirmaufzeichnungen. Beim Fallback werden sie nur für die eigene
KI-Aufnahme kurz versteckt. Die Option wird sofort für vorhandene Fenster
übernommen und lokal gespeichert. Bilder werden verkleinert, als JPEG übertragen
und nicht gespeichert oder in spätere Gesprächsrunden übernommen.
Ausschalten stoppt neue Aufnahmen. Bereits übertragene Bilder können noch
verarbeitet werden; verspätete Beobachtungen werden nach dem Stop verworfen.
Ein verstecktes Hauptmenü beendet die aktive Freigabe nicht; der Tray-Tooltip
zeigt den Freigabestatus. Über das Tray kann sie sofort ausgeschaltet werden.

## Einstellungen, Gespräche und Autostart

Standardverzeichnis: `%APPDATA%\EVA Desktop Agent\`.

- `settings.json`: Einstellungen und aktive Pose/Outfit, **keine Tokens**.
- `conversations.json`: bis zu 30 lokale Gespräche mit je bis zu 200 Textnachrichten.
- Tokens bleiben standardmäßig im RAM; optional werden sie im Windows-
  Anmeldeinformationstresor gespeichert.
- `EVA_DESKTOP_DATA_DIR` überschreibt den Datenordner für Entwicklung/Tests.

Autostart wird ausschließlich beim bewussten Speichern der entsprechenden
Einstellung gesetzt/gelöscht: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`,
Wert `EVADesktopAgent`. Es sind keine Administratorrechte nötig. Die Startdatei
verwendet einen absoluten Pfad und ist unabhängig vom Arbeitsordner beim Login.

## Eigene Outfit-Pakete

Struktur eines externen Pakets:

```text
mein-outfit/
  outfits/manifest.json
  poses/idle.png
  poses/standing.png
  expressions/neutral.png
```

Minimales Manifest:

```json
{
  "version": 1,
  "name": "Mein Outfit",
  "description": "Beschreibung",
  "poses": {
    "idle": {
      "frames": ["../poses/idle.png"],
      "scale": 1.0,
      "anchor": [0.5, 0.99],
      "frame_ms": 180,
      "note": "Einzelbild"
    }
  },
  "expressions": {"Neutral": "../expressions/neutral.png"}
}
```

Die unterstützten Zustandsnamen stehen in `app/character.py`. `idle` ist Pflicht;
fehlende Zustände greifen darauf zurück. Mehrere PNGs in `frames` aktivieren echte
Frame-Animation. Der Anker liegt im Bereich 0–1. Pfade müssen PNGs innerhalb des
Outfit-Paketverzeichnisses sein. Alle Frames werden vor dem Wechsel validiert.
Es wurde kein zusätzliches Outfit generiert.

## Architektur und Windows-Integration

Der bestehende Stack **Python + PySide6/Qt** bleibt erhalten. Er bietet native
Fenster, Alphatransparenz, System-Tray, skalierte Bilddarstellung und asynchrone
Signale ohne Webview oder permanente Game-Engine.

```text
desktop_agent/app/
  character.py   Outfit-Manifest, PNG-Cache, Zustandsautomat
  pet.py         Transparente Figur, Alphamaske, feste Anker
  windows.py     Taskleiste, Monitor-/DPI-Umrechnung, Hit-Testing, Autostart
  ui.py          Kleiner Chat und Gothic-Hauptmenü
  controller.py  Zustände, Interaktion, Gespräche, Bildschirmfreigabe
  ai.py          Austauschbare Backends, abbrechbares HTTP-Streaming
  storage.py     Einstellungen, lokale Gespräche, Windows-Tresor
  capture.py     Optionale Screenshot-Aufnahme
assets/character/  PNGs, Outfit-Manifest und Asset-Hinweise
assets/references/ Quelle der Ausdrucksporträts und historische Bildaufträge
```

Auf Windows werden Taskleistenfenster und die native Monitorinformation gelesen;
für die primäre Taskleiste dient außerdem `SHAppBarMessage(ABM_GETTASKBARPOS)` als
Fallback. Physische Koordinaten werden pro Monitor in Qt-Pixel umgerechnet.
Bei fehlender nativer Information verwendet EVA die Qt-Arbeitsfläche. Änderungen
werden über Screen-Signale und einen sparsamen Geometriecheck erfasst.

Die Figur ist ein rahmenloses Tool-Fenster mit Alphakanal und Alphamaske.
Die native Region und Layered-Window-Transparenz lassen transparente Bereiche
für andere Anwendungen frei; ergänzendes `WM_NCHITTEST` behandelt sichtbare Pixel.
Die Figur enthält keine künstliche Taskleiste und wird nicht als normales
Anwendungsfenster für Alt-Tab angelegt. Unveränderte Bilder werden gecacht;
bei Einzelbildern läuft kein Rendering-/Animationsloop.

Technische Quellen: [Windows Layered Windows](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features),
[WM_NCHITTEST](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest),
[Taskleisten auf weiteren Monitoren](https://devblogs.microsoft.com/oldnewthing/20141218-00/?p=43353),
[Qt QScreen](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QScreen.html).

## Paket bauen und prüfen

```bash
python3 -m tools.package_desktop
# Ergebnis: dist/EVA-Windows.zip
QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_companion tests.test_companion_gui -v
```

Die Paketierung verwendet eine feste Quellcode-Liste und ausschließlich die
öffentlichen Charakter-PNGs/Manifeste. `.env`, lokale Einstellungen, Tokens,
Gespräche und frühere Charakterentwürfe werden nicht eingepackt.

Die Qt-Tests prüfen Offline-Start, beide Chats, Menüseiten, Posen und Anker,
transparente Trefferbereiche, gesperrtes Ziehen, Persistenz, Outfit-Pfade,
Müdigkeit, Screenshots und HTTP-Streaming mit Zustandswechseln.

**Hier nicht als echte Windows-Abnahme geprüft:** Explorer-/Taskleistenbindung,
Click-through zu fremden Windows-Prozessen, Alt-Tab, Tray, Auto-Hide-Taskleiste,
Autostart, Windows-Tresor, gemischte Monitor-DPI, Windows-Capture-Affinity und
GPU-Leistung. Die Linux-Offscreen-Prüfung ersetzt diesen Zielrechnertest nicht.
Vertikale Taskleisten verwenden eine seitliche Randposition; eine tatsächlich
sitzende Pose ist für die untere horizontale Taskleiste optimiert.

Außerdem offen: echte Bewegungs- und Übergangsframes sowie zusätzlich
übersetzte Oberflächen.
