# EVA-Architektur

## Anfragepfad

```text
CLI -> EVA.receive_stream
    |- kurze feste Antworten oder direkte Module
    `- IntentRouter (kleines lokales Modell)
       |- optional: WebSearch / Wikipedia / Memory / RAG
       |- Wikipedia-Überblick -> direkte, gekürzte Quellenantwort
       `- sonst -> kompakter Prompt -> lokales Ollama-Modell
                    |- Textausgabe im Terminal
                    `- VoiceService -> XTTS-Worker -> Audioausgabe/Datei
    -> vollständige Antwort in History/Memory
```

Der Router kennt `NONE`, Webaktionen, `MEMORY`, `RAG`, `WEB_SEARCH_MEMORY` und `WEB_SEARCH_RAG`. Damit wird pgvector nur bei dokumentbezogenen Anfragen angesprochen. `core.activity` markiert aktive Anfragen und Ingestion; die Shutdown-Logik nutzt dieselben Zustände als Inhibitoren.

## Laufende Prozesse

`main.py` ist der Hauptprozess. Ollama läuft als eigener lokaler Dienst; die Sprachausgabe startet zusätzlich einen dauerhaften XTTS-Unterprozess, damit das Modell nicht für jeden Satz neu geladen wird. Der Hauptprozess übergibt Text über JSON-Zeilen an den Worker und erhält Audiodaten zurück. Ein Neustart von EVA ist deshalb nötig, wenn Voice-Werte aus `.env` geändert wurden.

## RAG

`rag.embeddings` kapselt Ollama und ermittelt die tatsächliche Vektordimension. `rag.postgres` verwaltet Pool, idempotentes Schema, Batch-Upserts, JSONB-/Source-Filter und HNSW-Cosine-Suche. `rag.retriever` erhält die kompatible `search(query, top_k=...)`-API und einen thread-sicheren TTL/LRU-Cache. Der bestehende JSON-RAG bleibt ausschließlich als expliziter `EVA_RAG_BACKEND=json`-Fallback erhalten.

## Drei getrennte Rechner

```text
Tapo -> EXTERNES SENTRY-PROJEKT (24/7, lokale Detection + Recognition)
          |- WoL + Status-State-Machine -> EVA-SERVER
          |                               |- EVA / Ollama / PostgreSQL / RAG
          |                               `- /health /presence /shutdown
          `- WoL + Ping-State-Machine --> DESKTOP-PC
                                          `- desktop_agent / Webcam
                                             `- desk_presence -> EVA /presence
```

Das externe Sentry-Projekt ist die einzige Power-Control-Instanz und besitzt keine Codeabhängigkeit zu diesem Repository. Die Netzwerkgrenze dieses EVA-Servers besteht aus `/health`, `/presence` und `/shutdown`. `interfaces.presence_state` fusioniert die eingehende Raum-Presence mit Desk-Presence für das EVA-Profil.

## Sicherheitsgrenzen

- Remote-Shutdown und Desktop Agent sind standardmäßig deaktiviert.
- Shutdown ist standardmäßig Dry-Run und benötigt mehrere positive Sicherheitsbedingungen.
- Enrollment erfolgt bewusst und lokal; gespeichert werden Deskriptoren, keine Frames.
- Unknown und Visitor können keinen privaten Memory-Kontext laden; ein persönliches Profil verlangt Desk-Bestätigung.
- Identity ersetzt nie Authentifizierung oder Bestätigung für sensible Aktionen.
