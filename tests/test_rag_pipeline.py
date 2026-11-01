import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from rag import RAGRetriever, RetrievalUnavailableError
from rag.json_store import RAGCreator
from tools.rag_ingest import ingest, new_document_id, split_text


class FakeEmbeddings:
    dimension = 3

    def detect_dimension(self):
        return 3

    def embed(self, text):
        return self.embed_many([text])[0]

    def embed_many(self, texts):
        vectors = []
        for text in texts:
            values = [float(text.lower().count("eva") + 1), float(len(text) % 7 + 1), 1.0]
            norm = sum(value * value for value in values) ** 0.5
            vectors.append([value / norm for value in values])
        return vectors


class MemoryStore:
    def __init__(self):
        self.rows = []
        self.search_calls = 0

    def insert_chunks(self, chunks):
        existing = {item["content"] for item in self.rows}
        fresh = [dict(item) for item in chunks if item["content"] not in existing]
        self.rows.extend(fresh)
        return len(fresh)

    def search(self, _vector, *, top_k, threshold, metadata_filter=None, source=None):
        self.search_calls += 1
        rows = self.rows
        if metadata_filter:
            rows = [
                row
                for row in rows
                if all(row["metadata"].get(k) == v for k, v in metadata_filter.items())
            ]
        if source:
            rows = [row for row in rows if row["metadata"].get("source") == source]
        return [
            {"id": index, "content": row["content"], "metadata": row["metadata"], "score": 0.9}
            for index, row in enumerate(rows[:top_k])
            if 0.9 >= threshold
        ]

    def health(self):
        return True

    def close(self):
        return None


class RAGPipelineTest(unittest.TestCase):
    def test_json_fallback_round_trip_and_search_after_module_move(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(RAGCreator, "_get_embedding", return_value=[1.0, 0.0, 0.0]),
        ):
            path = Path(directory) / "rag.json"
            store = RAGCreator(path)
            self.assertEqual(store.add_document("eva-doc", "EVA Wissen", {"source": "manual"}), 1)
            restored = RAGCreator(path)
            rows = restored.search("EVA", metadata_filter={"source": "manual"})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], "eva-doc")
            self.assertEqual(rows[0]["content"], "EVA Wissen")

    def retriever(self):
        store = MemoryStore()
        return RAGRetriever(
            "unused", embedding_client=FakeEmbeddings(), store=store, auto_migrate=False
        ), store

    def test_document_id_schema_and_chunking(self):
        self.assertEqual(
            new_document_id(1, datetime(2026, 8, 27, 22, 30)), "NEW_DOC_20260827_223000_0001"
        )
        chunks = split_text("eins zwei drei vier fünf sechs", 12, 2)
        self.assertGreater(len(chunks), 1)

    def test_batch_insertion_retrieval_filter_cache_and_duplicates(self):
        retriever, store = self.retriever()
        chunks = [
            {
                "document_id": "d1",
                "chunk_id": "c1",
                "content": "EVA Handbuch",
                "metadata": {"source": "manual", "lang": "de"},
            },
            {
                "document_id": "d1",
                "chunk_id": "c2",
                "content": "Anderer Inhalt",
                "metadata": {"source": "notes", "lang": "de"},
            },
        ]
        self.assertEqual(retriever.add_chunks(chunks), 2)
        self.assertEqual(retriever.add_chunks(chunks), 0)
        results = retriever.search("EVA", metadata_filter={"lang": "de"}, source="manual")
        self.assertEqual([item["content"] for item in results], ["EVA Handbuch"])
        self.assertIn("score", results[0])
        retriever.search("EVA", metadata_filter={"lang": "de"}, source="manual")
        self.assertEqual(store.search_calls, 1, "identische Suche muss aus dem TTL-Cache kommen")

    def test_ingestion_dry_run_needs_no_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "document.md")
            path.write_text("# EVA\n\nLokales Wissen", encoding="utf-8")
            result = ingest(path, dry_run=True, chunk_size=20, overlap=2)
            self.assertEqual(result["files"], 1)
            self.assertGreater(result["chunks"], 0)
            self.assertEqual(result["inserted"], 0)

    def test_postgres_unavailable_is_explicit(self):
        with self.assertRaises(RetrievalUnavailableError) as context:
            RAGRetriever("", embedding_dimension=3, embedding_client=FakeEmbeddings())
        self.assertIn("EVA_DATABASE_URL", str(context.exception))


if __name__ == "__main__":
    unittest.main()
