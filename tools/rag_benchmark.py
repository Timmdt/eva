from __future__ import annotations

import argparse
import time

from tools.rag_ingest import create_retriever


def milliseconds(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure real EVA RAG latency")
    parser.add_argument("query", nargs="?", default="Wie funktioniert EVA?")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    try:
        retriever = create_retriever()
    except Exception as exc:
        print(f"RAG benchmark unavailable: {exc}")
        return

    started = time.perf_counter()
    embedding = retriever.embedding_client.embed(args.query)
    embedding_ms = milliseconds(started)
    started = time.perf_counter()
    results = retriever.store.search(embedding, top_k=args.top_k, threshold=retriever.threshold)
    database_ms = milliseconds(started)
    started = time.perf_counter()
    _context = "\n---\n".join(item["content"] for item in results)
    context_ms = milliseconds(started)
    print(f"Embedding query: {embedding_ms:.1f} ms")
    print(f"Postgres retrieval: {database_ms:.1f} ms")
    print(f"Context build: {context_ms:.1f} ms")
    print(f"Total retrieval: {embedding_ms + database_ms + context_ms:.1f} ms")


if __name__ == "__main__":
    main()
