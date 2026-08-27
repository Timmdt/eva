# PostgreSQL-RAG

## Schema und Migration

Beim Erzeugen von `RAGRetriever` wird zunächst ein echtes Probe-Embedding erzeugt, sofern `EVA_EMBEDDING_DIMENSION=0` ist. Erst dann wird `rag_documents.embedding VECTOR(n)` mit dieser Dimension angelegt. Die zentrale Dimension wird zusätzlich in `rag_settings` dokumentiert.

`rag_documents` enthält `document_id`, `chunk_id`, Inhalt, SHA-256-Inhaltshash, Embedding, JSONB-Metadaten sowie Zeitstempel. `(document_id, chunk_id)` ist eindeutig. Gleiche Inhaltshashes werden vor einem Batch übersprungen. pgvector ab 0.5 erhält idempotent einen HNSW-Index mit `vector_cosine_ops`; ältere Versionen bleiben funktionsfähig, aber ohne HNSW.

## Ingestion

```bash
python3 -m tools.rag_ingest DATEI
python3 -m tools.rag_ingest ORDNER --recursive --chunk-size 1200 --overlap 120
python3 -m tools.rag_ingest DATEI --source handbuch --dry-run
```

Unterstützt werden UTF-8-Text, Markdown und JSON. PDF wird nur verwendet, wenn das optionale Paket `pypdf` installiert ist. Alle Chunks einer Ausführung werden gemeinsam eingebettet und mit `executemany` in einer Transaktion geschrieben; es gibt keinen Commit pro Chunk. IDs folgen `NEW_DOC_YYYYMMDD_HHMMSS_0001`.

## Retrieval und Ausfälle

`search()` unterstützt `top_k`, Score-Threshold, `metadata_filter`, `source` und liefert `id`, `content`, `metadata`, `score` sowie Dokument-/Chunk-ID. Identische Folgeabfragen werden kurzzeitig im TTL/LRU-Cache gehalten. Ein nicht erreichbares PostgreSQL erzeugt einen verständlichen `RetrievalUnavailableError`; EVA loggt den Ausfall und erfindet keine RAG-Ergebnisse. Der JSON-Fallback muss bewusst mit `EVA_RAG_BACKEND=json` aktiviert werden.

## Benchmark

`python3 -m tools.rag_benchmark "frage"` misst Query-Embedding, reine DB-Abfrage, Context-Build und Summe separat. Das Ziel von 15 ms betrifft nur `Postgres retrieval`; die Ausgabe enthält ausschließlich reale Laufzeiten.
