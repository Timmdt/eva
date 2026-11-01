from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class PostgresUnavailableError(RuntimeError):
    pass


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+(?:\.\d+)+)", value or "")
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


class PostgresVectorStore:
    """Thin pgvector store. psycopg is imported only when this backend is used."""

    def __init__(
        self,
        database_url: str,
        *,
        dimension: int,
        pool_min: int = 1,
        pool_max: int = 6,
        connect_timeout: float = 3.0,
    ) -> None:
        if not database_url:
            raise PostgresUnavailableError("EVA_DATABASE_URL ist nicht gesetzt.")
        if dimension <= 0:
            raise ValueError("Die Embedding-Dimension muss vor der Migration bekannt sein.")
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise PostgresUnavailableError(
                "PostgreSQL-Backend benötigt 'psycopg[binary,pool]'."
            ) from exc
        self.dimension = dimension
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=max(1, pool_min),
            max_size=max(pool_min, pool_max),
            timeout=connect_timeout,
            kwargs={"connect_timeout": max(1, int(connect_timeout))},
            open=False,
        )
        try:
            self._pool.open(wait=True, timeout=connect_timeout)
        except Exception as exc:
            raise PostgresUnavailableError(f"PostgreSQL ist nicht erreichbar: {exc}") from exc

    @contextmanager
    def connection(self) -> Iterator[Any]:
        try:
            with self._pool.connection() as connection:
                yield connection
        except PostgresUnavailableError:
            raise
        except Exception as exc:
            raise PostgresUnavailableError(f"PostgreSQL-Zugriff fehlgeschlagen: {exc}") from exc

    def migrate(self) -> dict[str, Any]:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cursor.fetchone()
                version = str(row[0]) if row else ""
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS rag_documents (
                        id BIGSERIAL PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        embedding VECTOR({self.dimension}) NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (document_id, chunk_id)
                    )
                """)
                cursor.execute("""
                    SELECT a.atttypmod
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    WHERE c.relname = 'rag_documents'
                      AND a.attname = 'embedding'
                      AND NOT a.attisdropped
                """)
                dimension_row = cursor.fetchone()
                existing_dimension = int(dimension_row[0]) if dimension_row else 0
                if existing_dimension > 0 and existing_dimension != self.dimension:
                    raise RuntimeError(
                        "Vorhandene rag_documents-Dimension "
                        f"{existing_dimension} passt nicht zum Modell ({self.dimension}). "
                        "Re-Embedding-Migration erforderlich."
                    )
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rag_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cursor.execute(
                    """
                    INSERT INTO rag_settings(key, value) VALUES ('embedding_dimension', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                """,
                    (str(self.dimension),),
                )
                hnsw = version_tuple(version) >= (0, 5, 0)
                if hnsw:
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS rag_documents_embedding_hnsw
                        ON rag_documents USING hnsw (embedding vector_cosine_ops)
                    """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS rag_documents_source_idx "
                    "ON rag_documents ((metadata->>'source'))"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS rag_documents_content_hash_idx "
                    "ON rag_documents (content_hash)"
                )
            connection.commit()
        return {"pgvector_version": version, "hnsw": hnsw, "dimension": self.dimension}

    def insert_chunks(self, chunks: list[dict[str, Any]]) -> int:
        if not chunks:
            return 0
        rows = []
        for chunk in chunks:
            content = str(chunk["content"]).strip()
            rows.append(
                (
                    str(chunk["document_id"]),
                    str(chunk["chunk_id"]),
                    content,
                    hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    vector_literal(chunk["embedding"]),
                    json.dumps(chunk.get("metadata") or {}, ensure_ascii=False),
                )
            )
        statement = """
            INSERT INTO rag_documents
                (document_id, chunk_id, content, content_hash, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)
            ON CONFLICT (document_id, chunk_id) DO UPDATE SET
                content = EXCLUDED.content, content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """
        with self.connection() as connection:
            with connection.cursor() as cursor:
                hashes = [row[3] for row in rows]
                cursor.execute(
                    "SELECT content_hash FROM rag_documents WHERE content_hash = ANY(%s)",
                    (hashes,),
                )
                existing = {str(row[0]) for row in cursor.fetchall()}
                unique_rows = []
                seen = set(existing)
                for row in rows:
                    if row[3] not in seen:
                        unique_rows.append(row)
                        seen.add(row[3])
                if unique_rows:
                    cursor.executemany(statement, unique_rows)
            connection.commit()
        return len(unique_rows)

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        threshold: float,
        metadata_filter: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        literal = vector_literal(vector)
        where = ["(1 - (embedding <=> %s::vector)) >= %s"]
        params: list[Any] = [literal, literal, threshold]
        if metadata_filter:
            where.append("metadata @> %s::jsonb")
            params.append(json.dumps(metadata_filter, ensure_ascii=False))
        if source:
            where.append("metadata->>'source' = %s")
            params.append(source)
        params.extend([literal, max(1, int(top_k))])
        statement = f"""
            SELECT id, document_id, chunk_id, content, metadata,
                   1 - (embedding <=> %s::vector) AS score
            FROM rag_documents
            WHERE {" AND ".join(where)}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "document_id": row[1],
                "chunk_id": row[2],
                "content": row[3],
                "metadata": row[4] if isinstance(row[4], dict) else json.loads(row[4]),
                "score": float(row[5]),
            }
            for row in rows
        ]

    def health(self) -> bool:
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
        return bool(row and row[0] == 1)

    def close(self) -> None:
        self._pool.close()
