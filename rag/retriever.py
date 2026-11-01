from __future__ import annotations

import hashlib
import json
from typing import Any

from .cache import TTLCache
from .embeddings import OllamaEmbeddingClient
from .postgres import PostgresUnavailableError, PostgresVectorStore


class RetrievalUnavailableError(RuntimeError):
    pass


class RAGRetriever:
    """Compatible ``search(query, top_k=...)`` facade backed by pgvector."""

    def __init__(
        self,
        database_url: str,
        *,
        embedding_model: str = "nomic-embed-text",
        embedding_dimension: int = 0,
        threshold: float = 0.45,
        top_k: int = 4,
        cache_ttl: float = 60.0,
        cache_size: int = 256,
        pool_min: int = 1,
        pool_max: int = 6,
        connect_timeout: float = 3.0,
        embedding_client: Any | None = None,
        store: Any | None = None,
        auto_migrate: bool = True,
    ) -> None:
        self.embedding_client = embedding_client or OllamaEmbeddingClient(embedding_model)
        self.threshold = float(threshold)
        self.top_k = int(top_k)
        self.cache = TTLCache(cache_size, cache_ttl)
        if store is None and not database_url:
            raise RetrievalUnavailableError("EVA_DATABASE_URL ist nicht gesetzt.")
        dimension = int(embedding_dimension) or self.embedding_client.detect_dimension()
        try:
            self.store = store or PostgresVectorStore(
                database_url,
                dimension=dimension,
                pool_min=pool_min,
                pool_max=pool_max,
                connect_timeout=connect_timeout,
            )
            self.migration_info = self.store.migrate() if auto_migrate else {}
        except PostgresUnavailableError as exc:
            raise RetrievalUnavailableError(str(exc)) from exc

    @staticmethod
    def _cache_key(
        query: str,
        top_k: int,
        threshold: float,
        metadata_filter: dict[str, Any] | None,
        source: str | None,
    ) -> str:
        payload = json.dumps(
            [query.strip().casefold(), top_k, threshold, metadata_filter or {}, source or ""],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def search(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
        *,
        metadata_filter: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        limit = self.top_k if top_k is None else max(1, int(top_k))
        minimum = self.threshold if threshold is None else float(threshold)
        key = self._cache_key(query, limit, minimum, metadata_filter, source)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            results = self.store.search(
                self.embedding_client.embed(query),
                top_k=limit,
                threshold=minimum,
                metadata_filter=metadata_filter,
                source=source,
            )
        except PostgresUnavailableError as exc:
            raise RetrievalUnavailableError(str(exc)) from exc
        self.cache.set(key, results)
        return results

    def add_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        embeddings = self.embedding_client.embed_many([str(chunk["content"]) for chunk in chunks])
        payload = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            item = dict(chunk)
            item["embedding"] = embedding
            payload.append(item)
        try:
            count = self.store.insert_chunks(payload)
        except PostgresUnavailableError as exc:
            raise RetrievalUnavailableError(str(exc)) from exc
        self.cache.clear()
        return count

    def health(self) -> bool:
        try:
            return bool(self.store.health())
        except Exception:
            return False

    def close(self) -> None:
        self.store.close()
