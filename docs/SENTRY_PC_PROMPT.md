# Kopierfertiger Prompt für den separaten Sentry-PC

```text
Du arbeitest direkt auf dem kleinen, stromsparenden 24/7-Sentry-PC. Erstelle hier ein eigenständiges Python-Projekt namens `eva-sentry`. Dieses Projekt darf keine Codeabhängigkeit zum EVA-Repository haben und muss funktionieren, während EVA-Server, Desktop-PC, Ollama und PostgreSQL ausgeschaltet sind.

WICHTIGE TOPOLOGIE

Es existieren drei getrennte Rechner:

1. SENTRY-PC
   - läuft dauerhaft
   - liest die Tapo-Kamera per RTSP
   - führt Face Detection und Face Recognition vollständig lokal aus
   - ist die einzige Power-Control-Instanz
   - weckt EVA-Server und Desktop-PC unabhängig per Wake-on-LAN

2. EVA-SERVER
   - läuft nicht dauerhaft
   - enthält EVA, Ollama, PostgreSQL, pgvector, RAG und Memory
   - stellt für Sentry HTTP-Endpunkte bereit

3. DESKTOP-PC
   - normaler Arbeitsplatz-PC
   - wird ebenfalls durch Sentry geweckt
   - wird niemals automatisch durch Sentry heruntergefahren

SICHERHEIT UND PRIVACY

- Keine Secrets, RTSP-Zugangsdaten, MAC-Adressen, IPs oder Tokens hardcoden.
- Alle sensiblen Werte ausschließlich über Environment/.env laden.
- `.env` ignorieren und nur `.env.example` committen.
- Kamera- und Gesichtsdaten niemals an Cloud-Dienste senden.
- Nur bewusst registrierte Personen speichern.
- Keine Datenbank unbekannter Personen anlegen.
- Frames standardmäßig niemals dauerhaft speichern.
- `EVA_FACE_SAVE_IMAGES=false` ist der sichere Default.
- Face Recognition ist kein sicherheitskritischer Authentifizierungsfaktor.
- Während Entwicklung niemals echte Shutdown-Aktionen ausführen.
- EVA-Server-Shutdown bleibt standardmäßig Dry-Run.
- Desktop-Shutdown bleibt vollständig deaktiviert.

PROJEKTSTRUKTUR

Erstelle mindestens:

sentry/
    __init__.py
    config.py
    camera.py
    face_detection.py
    face_recognition.py
    presence.py
    wol.py
    device_monitor.py
    power_manager.py
    event_bus.py
    state.py
    controller.py
    enroll.py
    main.py

tests/
deployment/systemd/eva-sentry.service
.env.example
.gitignore
requirements.txt
README.md

Start:

python3 -m sentry.main

Enrollment:

python3 -m sentry.enroll Tim --samples 10

KONFIGURATION

Unterstütze mindestens:

EVA_SENTRY_ENABLED=false
EVA_TAPO_RTSP_URL=
EVA_SENTRY_ALLOWED_USERS=Tim
EVA_SENTRY_FPS=2
EVA_SENTRY_FRAME_WIDTH=640
EVA_SENTRY_FRAME_HEIGHT=360
EVA_SENTRY_CAMERA_TIMEOUT=10
EVA_SENTRY_RECONNECT_DELAY=2

EVA_FACE_RECOGNITION_ENABLED=true
EVA_FACE_STORE=sentry/data/faces
EVA_FACE_THRESHOLD=0.82
EVA_FACE_ENROLLMENT_SAMPLES=10
EVA_FACE_SAVE_IMAGES=false

EVA_SERVER_MAC=
EVA_SERVER_IP=
EVA_SERVER_BROADCAST=255.255.255.255
EVA_SERVER_HEALTH_URL=http://EVA_SERVER_IP:8765/health
EVA_SERVER_PRESENCE_URL=http://EVA_SERVER_IP:8765/presence
EVA_SERVER_SHUTDOWN_URL=http://EVA_SERVER_IP:8765/shutdown
EVA_SERVER_CONTROL_TOKEN=
EVA_PRESENCE_TOKEN=

EVA_DESKTOP_MAC=
EVA_DESKTOP_IP=
EVA_DESKTOP_BROADCAST=255.255.255.255

EVA_PRESENCE_TIMEOUT=900
EVA_WOL_COOLDOWN=60
EVA_WOL_MAX_ATTEMPTS=3
EVA_DEVICE_BOOT_TIMEOUT=180
EVA_DEVICE_STATUS_INTERVAL=2
EVA_SENTRY_ALLOW_SERVER_WAKE=false
EVA_SENTRY_ALLOW_DESKTOP_WAKE=false
EVA_SENTRY_ALLOW_SERVER_SHUTDOWN=false
EVA_SENTRY_ALLOW_DESKTOP_SHUTDOWN=false

KAMERA

- Tapo RTSP über OpenCV lesen.
- Automatisch reconnecten, wenn Öffnen oder Lesen fehlschlägt.
- Frame Drops dürfen den Dienst nicht beenden.
- Connection-/Read-Timeouts setzen, soweit OpenCV sie unterstützt.
- Eingangsstream auf standardmäßig 640x360 skalieren.
- Nur 1–5 Detection-FPS zulassen; Default 2 FPS.
- Puffer klein halten, damit alte Frames verworfen werden.
- Keine 30-FPS-Verarbeitung.
- Kamerafehler loggen und weiter reconnecten.

ZWEISTUFIGE ERKENNUNG

Pipeline:

Frame
 -> leichte lokale Face Detection
 -> kein Gesicht: keine Recognition
 -> Gesicht vorhanden: lokale Identity Recognition
 -> registrierte und erlaubte Identity: Presence/Wake
 -> unbekannt/nicht erlaubt: Event, aber kein Wake

Face Detection und Face Recognition müssen getrennte Klassen/Module sein. Verwende eine leichtgewichtige lokale OpenCV-Lösung. Installiere keine großen Modelle blind. Optionale bessere Backends dürfen über eine klare Schnittstelle austauschbar sein.

ENROLLMENT

- Mehrere Frames pro Nutzer aufnehmen.
- Nur explizit über `python3 -m sentry.enroll <name>` registrieren.
- Ablage:

sentry/data/faces/Tim/profile.json
sentry/data/faces/Tim/embeddings.npy

- Mehrere normalisierte Embeddings pro Person speichern.
- Standardmäßig keine Originalbilder speichern.
- Namen validieren; keine Pfad-Traversal zulassen.
- Schreibvorgänge atomisch durchführen.

PERSONENZUSTÄNDE

NO_PERSON
UNKNOWN_PERSON
KNOWN_PERSON

Status enthält mindestens:

{
  "presence": true,
  "person_state": "KNOWN_PERSON",
  "identity": "Tim",
  "confidence": 0.91,
  "last_seen": "ISO-8601",
  "presence_started": "ISO-8601",
  "last_recognition": "ISO-8601"
}

Nur Identitäten aus `EVA_SENTRY_ALLOWED_USERS` dürfen Wake-on-LAN auslösen. Ein unbekanntes Gesicht darf keinen Rechner starten.

DUAL WAKE-ON-LAN

Implementiere `DeviceConfig` und `PowerManager` mit:

wake_device("eva_server")
wake_device("desktop")
wake_all_user_devices()

Bei erlaubter Identity beide Geräte unabhängig und möglichst parallel behandeln:

0. Wake-on-LAN für das Gerät nur ausführen, wenn der passende
   `EVA_SENTRY_ALLOW_*_WAKE`-Schalter aktiviert ist. Bei `false` ausschließlich
   Präsenz melden und keine Magic Packets senden.
1. Gerätestatus prüfen.
2. Wenn bereits online/ready: kein Magic Packet senden.
3. Sonst Magic Packet senden.
4. Pro Gerät eigenen Cooldown und eigene Versuchszahl führen.
5. Danach Status weiter pollen.
6. Nach maximalen Versuchen `ERROR`, keine Endlosschleife.
7. Ein Desktop-Fehler darf den EVA-Server nicht blockieren und umgekehrt.

Magic Packet lokal selbst erzeugen oder eine sehr kleine Bibliothek verwenden. Netzwerk und WoL in Tests vollständig mocken.

GERÄTEZUSTÄNDE

OFFLINE
WAKE_REQUESTED
BOOTING
ONLINE
READY
ERROR

EVA-Server:

OFFLINE -> WAKE_REQUESTED -> BOOTING -> ONLINE -> Health-Check -> READY

Desktop:

OFFLINE -> WAKE_REQUESTED -> BOOTING -> ONLINE

Für Version 1 reicht beim Desktop Ping. Beim EVA-Server zuerst Erreichbarkeit prüfen und anschließend `/health` bis `status=ready` pollen.

EVA-SERVER-API-VERTRAG

Der existierende EVA-Server stellt folgende Endpunkte bereit:

GET /health

Erwartete Antwort:

{
  "status": "ready",
  "ollama": true,
  "postgres": true,
  "rag": true,
  "eva": true,
  "active_request": false,
  "ingestion": false,
  "critical_task": false,
  "keep_awake": false,
  "presence": {}
}

POST /presence

Header, falls Token gesetzt:

Authorization: Bearer <EVA_PRESENCE_TOKEN>
Content-Type: application/json

Raum-Payload:

{
  "sensor": "room",
  "presence": true,
  "person_state": "KNOWN_PERSON",
  "identity": "Tim",
  "confidence": 0.91,
  "last_seen": "ISO-8601"
}

Sende nur bei Zustandsänderung und zusätzlich einen sparsamen Heartbeat, zum Beispiel alle 15 Sekunden. Wenn der EVA-Server offline ist, darf der Report den Kamera-Loop nicht blockieren. Verwende kurze Timeouts oder einen Hintergrund-Worker.

POST /shutdown

Header:

Authorization: Bearer <EVA_SERVER_CONTROL_TOKEN>
Content-Type: application/json

Der EVA-Server antwortet typischerweise:

- 202: angenommen oder Dry-Run
- 409: durch Activity-/Presence-/Keep-Awake-/Boot-Grace-Regel verhindert
- 401: Token falsch oder fehlt

Sentry darf `/shutdown` nur nach Presence-Timeout aufrufen und nur wenn `EVA_SENTRY_ALLOW_SERVER_SHUTDOWN=true`. Bei `false` ausschließlich `Would request EVA server shutdown.` loggen. Sentry darf niemals lokal `systemctl poweroff` ausführen.

PRESENCE UND SLEEP

- Erlaubte Identity aktualisiert `last_seen`.
- Beim ersten Eintritt `USER_ENTERED` auslösen und beide Geräte prüfen/wecken.
- Beim Verschwinden Timer starten, nicht sofort schlafen.
- Nach standardmäßig 15 Minuten `USER_LEFT` und höchstens eine Shutdown-Anfrage erzeugen.
- Neue erlaubte Presence hebt die Sleep-Anfrage auf.
- Unbekannte Presence darf kein Wake auslösen.
- Desktop niemals automatisch herunterfahren.

EVENT BUS

Implementiere einen kleinen lokalen Queue-EventBus ohne RabbitMQ/Kafka:

FACE_DETECTED
KNOWN_USER_DETECTED
UNKNOWN_USER_DETECTED
USER_ENTERED
USER_LEFT
EVA_SERVER_WAKE_REQUESTED
DESKTOP_WAKE_REQUESTED
EVA_SERVER_ONLINE
EVA_SERVER_READY
DESKTOP_ONLINE
EVA_SERVER_SLEEP_REQUESTED

PERFORMANCE

Kamera-/Detection-Pfad darf nicht durch Ping oder HTTP blockiert werden. Führe Gerätechecks parallel bzw. in Hintergrund-Threads/async Tasks aus. Messe im Debug-Logging echte Werte:

camera_fps
detection_ms
recognition_ms
cpu_percent

Keine Werte erfinden.

FAILURE BEHAVIOR

- Kameraausfall: Dienst läuft weiter und reconnectet.
- Internetausfall: lokale Erkennung und WoL funktionieren weiter.
- EVA-Server startet nicht: begrenzte Versuche, danach ERROR.
- Desktop startet nicht: EVA-Server-State-Machine läuft unabhängig weiter.
- HTTP-Reports: kurze Timeouts, kein Blockieren des Frame-Loops.
- Fehler eines einzelnen Frames: loggen, nächsten Frame verarbeiten.

SYSTEMD

Erstelle `deployment/systemd/eva-sentry.service`:

- After/Wants network-online.target
- Type=simple
- EnvironmentFile mit lokalem Pfad
- `ExecStart=<venv-python> -m sentry.main`
- Restart=always oder on-failure
- RestartSec=5
- WantedBy=multi-user.target
- NoNewPrivileges=true
- sinnvolle Hardening-Optionen
- Schreibzugriff nur auf den lokalen Face-/State-Ordner

Keine Unit automatisch installieren, aktivieren oder starten. Nur Vorlage und Anleitung liefern.

TESTS

Erstelle mindestens Tests für:

- Magic-Packet-Bytes und MAC-Validierung
- pro Gerät eigener WoL-Cooldown
- unbekanntes Gesicht weckt nichts
- erlaubtes Gesicht weckt beide Geräte
- unabhängige Gerätezustände
- ONLINE vs READY beim EVA-Server
- maximale Wake-Versuche führen zu ERROR
- Presence-Timeout
- neue Presence hebt Sleep-Anfrage auf
- Shutdown bleibt standardmäßig Dry-Run
- Desktop-Shutdown bleibt deaktiviert
- mehrere Enrollment-Embeddings
- registriertes vs unbekanntes Gesicht
- Privacy-Default speichert keine Frames
- Kamera-Reconnect/Frame-Drop mit Mocks
- HTTP 202/401/409 mit gemocktem EVA-Server
- Status-/HTTP-Arbeit blockiert den Kamera-Loop nicht

Tests dürfen keine echte Kamera öffnen, kein echtes WoL senden und keinen Rechner herunterfahren.

ABSCHLUSS

Führe Syntaxchecks und alle Tests aus. Dokumentiere danach:

- erstellte/geänderte Dateien
- Abhängigkeiten
- komplette `.env.example`
- Start- und Enrollment-Befehle
- systemd-Installation als manuellen Schritt
- Testresultate
- bekannte Hardwareeinschränkungen
- Dry-Run-Schritte vor Aktivierung

Wenn Kamera, MACs, IPs oder Tokens fehlen, implementiere alles mit Mocks und sicheren Defaults weiter. Keine echten Zugangsdaten erfinden und nicht wegen fehlender Hardware abbrechen.
```
