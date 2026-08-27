# Installation unter Ubuntu/Linux

## Python und Ollama

```bash
sudo apt update
sudo apt install python3-venv postgresql postgresql-contrib libpq-dev
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ollama pull qwen2.5:3b-instruct
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
cp .env.example .env
```

Für Kamera/PDF optional: `pip install -r requirements-optional.txt`. Auf einem Desktop kann statt `opencv-python-headless` das GUI-Paket `opencv-python` verwendet werden, aber nie beide parallel.

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

## Sentry-Werte

Trage lokal `EVA_TAPO_RTSP_URL`, `EVA_SERVER_MAC`, `EVA_SERVER_IP`, Broadcast und Health-URL ein. Starte zuerst mit:

```dotenv
EVA_SENTRY_ENABLED=true
EVA_SENTRY_MODE=presence_only
EVA_SENTRY_ALLOW_SHUTDOWN=false
```

Prüfe Logs, Readiness, Cooldown und alle Inhibitoren mehrere Tage. Aktiviere echten Shutdown erst danach bewusst. Enrollment ist optional; alle Kamera-/Face-Schritte bleiben lokal.
