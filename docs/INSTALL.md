# Installation unter Ubuntu/Linux

## Python und Ollama

```bash
sudo apt update
sudo apt install python3-venv postgresql postgresql-contrib libpq-dev
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ollama pull gemma4:e2b
ollama pull nomic-embed-text
cp .env.example .env
```

Für Kamera/PDF optional: `pip install -r requirements-optional.txt`. Auf einem Desktop kann statt `opencv-python-headless` das GUI-Paket `opencv-python` verwendet werden, aber nie beide parallel.

Für den Windows-Begleiter mit serverseitiger Text- und Bildverarbeitung gilt die
separate Anleitung [DESKTOP_SERVER_LINK.md](DESKTOP_SERVER_LINK.md).

## PostgreSQL und pgvector

Installiere das zu deiner Ubuntu/PostgreSQL-Version passende pgvector-Paket (oft `postgresql-<major>-pgvector`) oder pgvector nach dessen offizieller Anleitung. Danach lokal und mit einem eigenen Passwort:

```sql
CREATE USER eva WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE eva OWNER eva;
\c eva
CREATE EXTENSION IF NOT EXISTS vector;
```

Setze `EVA_DATABASE_URL` in `.env`. EVA prüft die Extension-Version, bestimmt die Modelldimension und führt die idempotente Tabellen-/Indexmigration beim ersten RAG-Start aus. Ein Dimensionswechsel des Embedding-Modells erfordert eine bewusst geplante Re-Embedding-Migration; nicht einfach `EVA_EMBEDDING_DIMENSION` ändern.

Für eine rein lokale Installation kann EVA ohne Datenbankpasswort per Unix-Socket und Peer-Authentifizierung laufen:

```bash
./tools/setup_postgres.sh
# .env:
export EVA_DATABASE_URL='postgresql:///eva'
```

Das Setup-Skript legt idempotent eine PostgreSQL-Rolle mit dem Namen des aktuellen Linux-Benutzers, die Datenbank `eva` und die pgvector-Extension an. Es benötigt einmalig das lokale sudo-Passwort.

## Health und systemd

Der Health-Server kann aus einem eigenen Launcher mit `interfaces.health_server.serve(eva, host, port)` gestartet werden. Vorlagen liegen in `deployment/systemd`; prüfe Benutzer, Pfade und Dependencies vor dem manuellen Kopieren nach `/etc/systemd/system`. Dieses Repository führt weder `sudo` noch `systemctl enable/start` automatisch aus.

Für den systemd-Betrieb setze `EVA_HEALTH_ENABLED=true` und eine für den kleinen Server erreichbare `EVA_HEALTH_HOST`-Adresse. `ExecStartPre=python -m tools.wait_dependencies` wartet auf Ollama, PostgreSQL, pgvector und die RAG-Migration; erst danach startet der EVA-Prozess.

## Externer Sentry-PC

Der Sentry-PC verwendet ein eigenes Repository und wird nicht aus diesem EVA-Projekt installiert. Der vollständige Implementierungsauftrag steht in `docs/SENTRY_PC_PROMPT.md`.

Auf dem EVA-Server müssen `EVA_HEALTH_ENABLED=true`, eine vom Sentry-Netz erreichbare `EVA_HEALTH_HOST`-Adresse sowie mit dem externen Sentry-PC übereinstimmende `EVA_SERVER_CONTROL_TOKEN`- und `EVA_PRESENCE_TOKEN`-Werte gesetzt werden. Beschränke Port 8765 per Firewall auf Sentry- und Desktop-IP. `EVA_ALLOW_REMOTE_SHUTDOWN=false` bleibt zunächst Dry-Run; aktiviere echten Shutdown erst nach mehrtägiger Prüfung aller Inhibitoren.

Auf dem Desktop werden die optionalen OpenCV-Abhängigkeiten, ein lokaler bewusst kopierter Face-Store und `EVA_DESKTOP_AGENT_ENABLED=true` benötigt. Start ist `python3 -m desktop_agent.main`; die optionale Vorlage liegt in `deployment/systemd/eva-desktop-agent.service`. Der Desktop-Agent kann keine Geräte wecken oder herunterfahren.
