from __future__ import annotations

import argparse
import time
from typing import Callable

from core.eva import EVA


def measure(call: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    result = call()
    return result, (time.perf_counter() - started) * 1000.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure real EVA routing/RAG/LLM latency")
    parser.add_argument("query", nargs="?", default="Fasse das EVA-Handbuch kurz zusammen.")
    args = parser.parse_args()
    eva = EVA(run_module_tests=False)
    total_started = time.perf_counter()

    decision, router_ms = measure(lambda: eva._route_intent(args.query))
    print(f"IntentRouter latency: {router_ms:.1f} ms ({decision.action})")

    if eva.rag is None:
        print("Query embedding: unavailable (RAG backend/model not ready)")
        print("Vector retrieval: unavailable (RAG backend/model not ready)")
        print("Full RAG retrieval: unavailable (RAG backend/model not ready)")
    else:
        embedding, embedding_ms = measure(lambda: eva.rag.embedding_client.embed(args.query))
        _rows, vector_ms = measure(lambda: eva.rag.store.search(
            embedding, top_k=eva.rag_top_k, threshold=float(eva.cfg.get("rag_threshold", 0.45))))
        _context, rag_ms = measure(lambda: eva._build_rag_context(args.query))
        print(f"Query embedding: {embedding_ms:.1f} ms")
        print(f"Vector retrieval: {vector_ms:.1f} ms")
        print(f"Full RAG retrieval: {rag_ms:.1f} ms")

    started = time.perf_counter()
    try:
        stream = eva.generate_response_stream(args.query)
        first = next(stream)
        first_token_ms = (time.perf_counter() - started) * 1000.0
        for _chunk in stream:
            pass
        print(f"Ollama first-token latency: {first_token_ms:.1f} ms ({len(first)} chars first chunk)")
    except Exception as exc:
        print(f"Ollama first-token latency: unavailable ({exc})")
    print(f"Total benchmark latency: {(time.perf_counter() - total_started) * 1000.0:.1f} ms")


if __name__ == "__main__":
    main()
