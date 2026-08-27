# EVA

EVA ist ein modularer, lokal betriebener Python-Assistent mit Ollama, semantischem Intent-Routing, Memory, Websuche und PostgreSQL/pgvector-RAG. Antworten werden im Terminal gestreamt und danach vollständig in History/Memory gespeichert.

Neu enthalten sind außerdem ein lokaler Sentry-Dienst für RTSP-Presence/Wake-on-LAN sowie ein Visual Cortex für Desktop-Präsenz und bewusst registrierte Benutzer. Kamera- und Gesichtsdaten werden nicht an Cloud-Dienste übertragen; Frames werden standardmäßig nicht gespeichert. Gesichtserkennung ist ausdrücklich kein Authentifizierungsfaktor für kritische Aktionen.

## Schnellstart

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama pull qwen2.5:3b-instruct
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
python3 main.py
```

PostgreSQL/pgvector muss vorher lokal eingerichtet und `EVA_DATABASE_URL` gesetzt sein. Die Tabelle und ein HNSW-Cosine-Index werden beim ersten erfolgreichen RAG-Start idempotent erstellt.

Auf einem lokalen Ubuntu-System kann `./tools/setup_postgres.sh` Rolle, Datenbank und pgvector per Peer-Authentifizierung vorbereiten. Das Skript benötigt einmalig sudo; EVA selbst läuft danach ohne Root-Rechte.

Wichtige Befehle:

```bash
python3 -m tools.rag_ingest ./docs --recursive --source eva-docs
python3 -m tools.rag_ingest ./example.md --dry-run
python3 -m tools.rag_benchmark "EVA Architektur"
python3 -m tools.eva_benchmark "Fasse das EVA-Handbuch zusammen"
python3 -m sentry.enroll Tim
python3 -m unittest discover -s tests -v
```

Weitere Details: [Architektur](docs/ARCHITECTURE.md), [RAG](docs/RAG.md), [Sentry](docs/SENTRY.md), [Visual Cortex](docs/VISUAL_CORTEX.md), [Installation](docs/INSTALL.md).
