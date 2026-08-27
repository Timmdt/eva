# EVA-Architektur

## Anfragepfad

```text
CLI -> EVA.receive_stream
    -> direkte Module
    -> IntentRouter (kleines lokales Modell)
       -> optional WebSearch / Memory / RAG
    -> kompakter Prompt
    -> Ollama stream=True + keep_alive
    -> Terminal-Stream
    -> vollständige History/Memory
```

Der Router kennt `NONE`, Webaktionen, `MEMORY`, `RAG`, `WEB_SEARCH_MEMORY` und `WEB_SEARCH_RAG`. Damit wird pgvector nur bei dokumentbezogenen Anfragen angesprochen. `core.activity` markiert aktive Anfragen und Ingestion; die Shutdown-Logik nutzt dieselben Zustände als Inhibitoren.

## RAG

`rag.embeddings` kapselt Ollama und ermittelt die tatsächliche Vektordimension. `rag.postgres` verwaltet Pool, idempotentes Schema, Batch-Upserts, JSONB-/Source-Filter und HNSW-Cosine-Suche. `rag.retriever` erhält die kompatible `search(query, top_k=...)`-API und einen thread-sicheren TTL/LRU-Cache. Der bestehende JSON-RAG bleibt ausschließlich als expliziter `EVA_RAG_BACKEND=json`-Fallback erhalten.

## Power Grid und Visual Cortex

```text
Tapo RTSP -> Small Server / Sentry -> Presence / optionale Identity
          -> ServerStatus -> Wake-on-LAN -> Big EVA Server
                                           |- Ollama
                                           |- PostgreSQL/pgvector
                                           `- /health

Desktop Webcam -> Visual Cortex -> PresenceState / Identity -> EventBus -> EVA-Profil
```

`core.events.EventBus` transportiert Presence-, Identity-, Wake-, Ready- und Sleep-Ereignisse prozessintern. Für verteilte Hosts ist der Health-Endpunkt die Netzwerkgrenze; ein externer Broker ist bewusst nicht erforderlich.

## Sicherheitsgrenzen

- Sentry und Visual Cortex sind standardmäßig deaktiviert.
- Shutdown ist standardmäßig Dry-Run und benötigt mehrere positive Sicherheitsbedingungen.
- Enrollment erfolgt bewusst und lokal; gespeichert werden Deskriptoren, keine Frames.
- Unknown und Visitor können bei aktivierter Profil-Isolation keinen privaten Memory-Kontext laden.
- Identity ersetzt nie Authentifizierung oder Bestätigung für sensible Aktionen.
