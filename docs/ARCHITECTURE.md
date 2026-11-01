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

Das externe Sentry-Projekt ist die einzige Power-Control-Instanz und besitzt keine Codeabhängigkeit zu diesem Repository. Es verwendet ausschließlich `/health`, `/presence` und `/shutdown` des EVA-Servers. `interfaces.presence_state` fusioniert die eingehende Raum-Presence mit Desk-Presence für das EVA-Profil.

## EVA auf dem Windows-Haupt-PC

`desktop_agent.companion` startet die modulare Qt-Anwendung in `desktop_agent/app/`
mit dem Gothic-Anime-Charakter aus dem bereitgestellten Character Sheet,
Taskleisten-Verankerung, kleinem Chat, Hauptmenü, lokalen Unterhaltungen und
optionalen Screenshots eines ausgewählten Monitors.
Sie läuft auf dem Haupt-PC und benötigt dort weder EVAs Kern noch eine Datenbank.
Die separat gestartete `desktop_agent.companion_server`-Bridge läuft auf dem
EVA-Rechner, stellt `/desktop/status` und `/desktop/chat` auf Port 8766 bereit und
leitet Text/Bilder an den lokalen Ollama-Dienst weiter. Sie ist durch einen
eigenen Token geschützt und standardmäßig an Loopback gebunden.

Normale Gespräche und ausdrücklich bildschirmbezogene Anfragen werden getrennt:
`EVA_COMPANION_CHAT_MODEL` wählt das Gesprächsmodell, `EVA_COMPANION_MODEL` das
Bildmodell. Nur Bildschirmfragen und regelmäßige Beobachtungen erhalten Bilder;
überflüssige Screenshots älterer Clients werden serverseitig verworfen. Kurze
Gesprächsregeln und separate Regeln für belegbare Bilddetails ersetzen die
frühere ausführliche Rollenbeschreibung.

Der Desktop speichert eigene lokale Unterhaltungen. EVAs zentraler Langzeitspeicher,
Identitätsfusion, Module und Stimme werden darüber noch nicht angesprochen.
Bildschirmfreigabe ist bei jedem Start aus. Bilder werden weder als Dateien
gespeichert noch in den Chatverlauf aufgenommen. Es gibt keine Computersteuerung.
Installation, Windows-Paket und Modellwahl: [DESKTOP_COMPANION.md](DESKTOP_COMPANION.md).

## Sicherheitsgrenzen

- Remote-Shutdown und Desktop Agent sind standardmäßig deaktiviert.
- Shutdown ist standardmäßig Dry-Run und benötigt mehrere positive Sicherheitsbedingungen.
- Enrollment erfolgt bewusst und lokal; gespeichert werden Deskriptoren, keine Frames.
- Unknown und Visitor können keinen privaten Memory-Kontext laden; ein persönliches Profil verlangt Desk-Bestätigung.
- Identity ersetzt nie Authentifizierung oder Bestätigung für sensible Aktionen.
