import hashlib
import json
import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    import ollama
except ImportError:
    ollama = None


logger = logging.getLogger(__name__)


class RAGCreator:
    """
    Kleine lokale RAG-Datenbank für EVA.

    Eigenschaften:
    - lokale JSON-Datenbank
    - Embeddings über Ollama
    - Cosine Similarity
    - Embedding-Cache: unveränderter Text wird nicht neu eingebettet
    - automatische Normalisierung der Vektoren
    - Metadaten
    - einfache Dokument-/Chunk-Verwaltung
    - atomisches Speichern
    - DB-Versionierung
    """

    DB_VERSION = 2

    def __init__(
        self,
        storage_path: str | Path = "rag_db.json",
        embedding_model: str = "nomic-embed-text",
        similarity_threshold: float = 0.45,
        max_results: int = 5,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.max_results = max_results
        self.documents: list[dict[str, Any]] = []

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.load_db()

    # ------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------

    def _get_embedding(self, text: str) -> list[float]:
        if ollama is None:
            raise RuntimeError(
                "Das Python-Paket 'ollama' ist nicht installiert."
            )

        text = text.strip()
        if not text:
            raise ValueError("Ein leerer Text kann nicht eingebettet werden.")

        response = ollama.embeddings(
            model=self.embedding_model,
            prompt=text,
        )

        embedding = response.get("embedding")
        if not embedding:
            raise RuntimeError(
                "Ollama hat kein Embedding zurückgegeben."
            )

        return self._normalize_vector(embedding)

    @staticmethod
    def _normalize_vector(vector: list[float]) -> list[float]:
        arr = [float(value) for value in vector]
        norm = math.sqrt(sum(value * value for value in arr))
        if norm == 0:
            raise ValueError("Embedding besitzt die Länge 0.")
        return [value / norm for value in arr]

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(
            text.strip().encode("utf-8")
        ).hexdigest()

    # ------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------

    def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int = 80,
    ) -> int:
        """
        Fügt ein Dokument hinzu.

        Gibt die Anzahl erzeugter Chunks zurück.

        Beispiel:
            rag.add_document(
                "lumora_design",
                langer_text,
                {"source": "lumora.md", "type": "project"},
            )
        """
        content = content.strip()

        if not content:
            raise ValueError("Dokumentinhalt darf nicht leer sein.")

        if chunk_size and len(content) > chunk_size:
            chunks = self._split_text(
                content,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )
        else:
            chunks = [content]

        added = 0

        for index, chunk in enumerate(chunks):
            chunk_id = (
                doc_id
                if len(chunks) == 1
                else f"{doc_id}::chunk_{index}"
            )

            chunk_metadata = dict(metadata or {})
            chunk_metadata.update(
                {
                    "parent_id": doc_id,
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                }
            )

            if self.upsert_document(
                chunk_id,
                chunk,
                chunk_metadata,
            ):
                added += 1

        self.save_db()
        return added

    def upsert_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Erstellt oder aktualisiert einen einzelnen Eintrag.

        True = Embedding wurde neu erzeugt.
        False = vorhandener unveränderter Eintrag wurde wiederverwendet.
        """
        content = content.strip()

        if not content:
            raise ValueError("Dokumentinhalt darf nicht leer sein.")

        new_hash = self._content_hash(content)

        existing_index = next(
            (
                index
                for index, doc in enumerate(self.documents)
                if str(doc.get("id")) == str(doc_id)
            ),
            None,
        )

        # Unverändert -> kein teures Embedding nötig.
        if existing_index is not None:
            existing = self.documents[existing_index]

            if existing.get("content_hash") == new_hash:
                existing["metadata"] = metadata or existing.get(
                    "metadata", {}
                )
                return False

        embedding = self._get_embedding(content)

        document = {
            "id": str(doc_id),
            "content": content,
            "content_hash": new_hash,
            "embedding_model": self.embedding_model,
            "embedding": embedding,
            "metadata": metadata or {},
        }

        if existing_index is None:
            self.documents.append(document)
        else:
            self.documents[existing_index] = document

        return True

    def delete_document(self, doc_id: str) -> bool:
        old_length = len(self.documents)

        self.documents = [
            doc
            for doc in self.documents
            if str(doc.get("id")) != str(doc_id)
        ]

        changed = len(self.documents) != old_length

        if changed:
            self.save_db()

        return changed

    def clear(self) -> None:
        self.documents = []
        self.save_db()

    # ------------------------------------------------------------
    # Search
    # ------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 3,
        threshold: float | None = None,
        *,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantische Suche.

        Rückgabe:
        [
            {
                "id": "...",
                "content": "...",
                "metadata": {...},
                "score": 0.81,
            }
        ]
        """
        query = query.strip()

        if not query or not self.documents:
            return []

        query_embedding = self._normalize_vector(
            self._get_embedding(query)
        )

        threshold_value = (
            self.similarity_threshold
            if threshold is None
            else threshold
        )

        results: list[dict[str, Any]] = []

        for document in self.documents:
            if not self._metadata_matches(
                document.get("metadata", {}),
                metadata_filter,
            ):
                continue

            try:
                doc_embedding = self._normalize_vector(
                    document["embedding"]
                )
            except (KeyError, ValueError, TypeError):
                logger.warning(
                    "Ungültiges Embedding für Dokument %s.",
                    document.get("id"),
                )
                continue

            # Weil beide Vektoren normalisiert sind:
            # Cosine Similarity == Dot Product
            score = float(sum(
                left * right
                for left, right in zip(query_embedding, doc_embedding, strict=True)
            ))

            if score >= threshold_value:
                result = dict(document)
                result["score"] = score
                results.append(result)

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        limit = max(
            1,
            min(
                int(top_k),
                self.max_results,
            ),
        )

        return results[:limit]

    @staticmethod
    def _metadata_matches(
        metadata: dict[str, Any],
        required: dict[str, Any] | None,
    ) -> bool:
        if not required:
            return True

        for key, expected in required.items():
            if metadata.get(key) != expected:
                return False

        return True

    # ------------------------------------------------------------
    # Text splitting
    # ------------------------------------------------------------

    @staticmethod
    def _split_text(
        text: str,
        chunk_size: int = 1200,
        overlap: int = 80,
    ) -> list[str]:
        if chunk_size <= 0:
            raise ValueError("chunk_size muss > 0 sein.")

        if overlap < 0 or overlap >= chunk_size:
            raise ValueError(
                "overlap muss >= 0 und kleiner als chunk_size sein."
            )

        # Absatzweise zuerst schneiden.
        paragraphs = [
            paragraph.strip()
            for paragraph in text.split("\n\n")
            if paragraph.strip()
        ]

        if not paragraphs:
            return []

        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            candidate = (
                f"{current}\n\n{paragraph}".strip()
                if current
                else paragraph
            )

            if len(candidate) <= chunk_size:
                current = candidate
                continue

            if current:
                chunks.append(current)

                # Kleiner Überlapp aus dem alten Chunk.
                tail = current[-overlap:] if overlap else ""
                current = (
                    f"{tail}\n\n{paragraph}".strip()
                    if tail
                    else paragraph
                )

                if len(current) <= chunk_size:
                    continue

            # Einzelner Absatz ist schon zu groß.
            while len(current) > chunk_size:
                chunks.append(current[:chunk_size].strip())
                step = chunk_size - overlap
                current = current[step:].strip()

        if current:
            chunks.append(current)

        return [chunk for chunk in chunks if chunk]

    # ------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------

    def save_db(self) -> None:
        data = {
            "version": self.DB_VERSION,
            "embedding_model": self.embedding_model,
            "documents": self.documents,
        }

        self._atomic_write(data)

    def load_db(self) -> None:
        if not self.storage_path.exists():
            self.documents = []
            return

        try:
            with self.storage_path.open(
                "r",
                encoding="utf-8",
            ) as handle:
                raw = json.load(handle)

            # Neue DB-Struktur
            if isinstance(raw, dict):
                self.documents = raw.get(
                    "documents",
                    [],
                )

                stored_model = raw.get(
                    "embedding_model"
                )

                if (
                    stored_model
                    and stored_model != self.embedding_model
                ):
                    logger.warning(
                        "RAG-Datenbank verwendet Embedding-Modell '%s', "
                        "aktuell konfiguriert ist '%s'. "
                        "Bei einem Modellwechsel sollten die Embeddings "
                        "neu aufgebaut werden.",
                        stored_model,
                        self.embedding_model,
                    )

            # Alte DB-Struktur aus deiner bisherigen Version:
            # direktes Array von Dokumenten.
            elif isinstance(raw, list):
                self.documents = raw

            else:
                raise ValueError(
                    "Unbekanntes RAG-Datenbankformat."
                )

            if not isinstance(self.documents, list):
                self.documents = []

            logger.info(
                "RAG geladen: %d Dokumente.",
                len(self.documents),
            )

        except (OSError, json.JSONDecodeError, ValueError):
            logger.exception(
                "RAG-Datenbank konnte nicht geladen werden."
            )
            self.documents = []

    def rebuild_embeddings(self) -> int:
        """
        Embeddings aller Dokumente mit dem aktuell konfigurierten Modell
        neu erzeugen.

        Nützlich nach einem Embedding-Modellwechsel.
        """
        count = 0

        for document in self.documents:
            content = str(
                document.get("content", "")
            ).strip()

            if not content:
                continue

            document["embedding"] = self._get_embedding(
                content
            )
            document["embedding_model"] = self.embedding_model
            document["content_hash"] = self._content_hash(
                content
            )

            count += 1

        self.save_db()
        return count

    def _atomic_write(
        self,
        data: dict[str, Any],
    ) -> None:
        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temp_name = tempfile.mkstemp(
            dir=str(self.storage_path.parent),
            prefix=f"{self.storage_path.name}.",
            suffix=".tmp",
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    data,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )

            os.replace(
                temp_name,
                self.storage_path,
            )

        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)
