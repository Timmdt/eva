# EVA

Neu im Projekt? Beginne mit dem [EVA-Entwicklerleitfaden](docs/ENTWICKLERLEITFADEN.md). Er zeigt den Anfragefluss, die wichtigsten Dateien und die zentralen Funktionen in kurzer Form.

Lokale XTTS-v2-Sprachausgabe und Streaming: [docs/VOICE.md](docs/VOICE.md)

Lokaler Browser-Chat mit Sprachausgabe: [docs/WEB_UI.md](docs/WEB_UI.md)

EVA ist ein modularer, lokal betriebener Python-Assistent mit Ollama, semantischem Intent-Routing, Memory, Websuche und PostgreSQL/pgvector-RAG. Antworten werden im Terminal oder Browser gestreamt und danach vollständig in History/Memory gespeichert.

Der Sentry-PC ist bewusst ein getrenntes Projekt und nicht Bestandteil dieses Repositories. EVA stellt dafür ausschließlich die lokalen, token-geschützten Gegenstellen `/health`, `/presence` und `/shutdown` bereit. Ein kopierfertiger Implementierungsauftrag liegt in `docs/SENTRY_PC_PROMPT.md`. Der optionale Desktop-Agent ergänzt Schreibtisch-Präsenz; Gesichtserkennung ist ausdrücklich kein Authentifizierungsfaktor für kritische Aktionen.

## Schnellstart

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama pull gemma4:e2b
# Optional für den späteren Desktop-Agenten:
ollama pull maternion/mai-ui:2b
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
python3 -m desktop_agent.main
python3 -m unittest discover -s tests -v
```

Weitere Details: [Entwicklerleitfaden](docs/ENTWICKLERLEITFADEN.md), [Architektur](docs/ARCHITECTURE.md), [Weboberfläche](docs/WEB_UI.md), [Voice](docs/VOICE.md), [LLM-/TTS-Benchmark](docs/LLM_TTS_BENCHMARK.md), [RAG](docs/RAG.md), [Sentry-PC-Prompt](docs/SENTRY_PC_PROMPT.md), [Visual Cortex](docs/VISUAL_CORTEX.md), [Präsenz-Automation](docs/PRESENCE_AUTOMATION.md), [Installation](docs/INSTALL.md).
