from __future__ import annotations

import argparse
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from core.activity import INGESTION_LOCK, activity_registry
from core.config import EVA_CONFIG
from rag import RAGRetriever

SUPPORTED_SUFFIXES = {".txt", ".md", ".json", ".pdf"}


def new_document_id(counter: int, now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return f"NEW_DOC_{stamp}_{counter:04d}"


def split_text(text: str, chunk_size: int = 1200, overlap: int = 120) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk-size muss größer als 0 sein")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap muss zwischen 0 und chunk-size - 1 liegen")
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + chunk_size)
        end = hard_end
        if hard_end < len(text):
            candidates = [text.rfind(marker, start, hard_end) for marker in ("\n\n", "\n", ". ", " ")]
            boundary = max(candidates)
            if boundary > start + chunk_size // 2:
                end = boundary + (2 if text[boundary:boundary + 2] == "\n\n" else 1)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        next_start = end - overlap
        start = next_start if next_start > start else end
    return chunks


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(value, ensure_ascii=False, indent=2)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("PDF benötigt optional 'pypdf'; Text/Markdown/JSON funktionieren ohne.") from exc
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    raise ValueError(f"Nicht unterstütztes Dateiformat: {path.suffix}")


def iter_files(target: Path, recursive: bool = False) -> Iterator[Path]:
    if target.is_file():
        if target.suffix.lower() in SUPPORTED_SUFFIXES:
            yield target
        return
    pattern = "**/*" if recursive else "*"
    for path in sorted(target.glob(pattern)):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def build_chunks(path: Path, document_id: str, chunk_size: int, overlap: int,
                 source: str | None = None) -> list[dict[str, Any]]:
    parts = split_text(read_document(path), chunk_size, overlap)
    return [{
        "document_id": document_id,
        "chunk_id": f"{document_id}::chunk_{index:04d}",
        "content": part,
        "metadata": {"source": source or str(path), "file_name": path.name,
                     "chunk_index": index, "chunk_count": len(parts)},
    } for index, part in enumerate(parts)]


def create_retriever() -> RAGRetriever:
    cfg = EVA_CONFIG
    return RAGRetriever(
        str(cfg.get("rag_database_url", "")),
        embedding_model=str(cfg.get("rag_embedding_model", "nomic-embed-text")),
        embedding_dimension=int(cfg.get("rag_embedding_dimension", 0)),
        threshold=float(cfg.get("rag_threshold", 0.45)),
        top_k=int(cfg.get("rag_top_k", 4)),
        cache_ttl=float(cfg.get("rag_cache_ttl", 60.0)),
        cache_size=int(cfg.get("rag_cache_size", 256)),
        pool_min=int(cfg.get("rag_pool_min", 1)),
        pool_max=int(cfg.get("rag_pool_max", 6)),
        connect_timeout=float(cfg.get("rag_connect_timeout", 3.0)),
    )


@contextmanager
def ingestion_activity() -> Iterator[None]:
    INGESTION_LOCK.write_text(str(datetime.now().isoformat()), encoding="utf-8")
    try:
        with activity_registry.track("ingestion"):
            yield
    finally:
        INGESTION_LOCK.unlink(missing_ok=True)


def ingest(target: Path, *, recursive: bool = False, chunk_size: int = 1200,
           overlap: int = 120, source: str | None = None, dry_run: bool = False,
           retriever: Any | None = None) -> dict[str, int]:
    files = list(iter_files(target, recursive))
    chunks: list[dict[str, Any]] = []
    for counter, path in enumerate(files, start=1):
        chunks.extend(build_chunks(path, new_document_id(counter), chunk_size, overlap, source))
    if dry_run:
        return {"files": len(files), "chunks": len(chunks), "inserted": 0}
    if not chunks:
        return {"files": len(files), "chunks": 0, "inserted": 0}
    with ingestion_activity():
        backend = retriever or create_retriever()
        inserted = backend.add_chunks(chunks)
    return {"files": len(files), "chunks": len(chunks), "inserted": inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ingestion for EVA pgvector RAG")
    parser.add_argument("target", type=Path)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--overlap", type=int, default=120)
    parser.add_argument("--source")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = ingest(args.target, recursive=args.recursive, chunk_size=args.chunk_size,
                    overlap=args.overlap, source=args.source, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
