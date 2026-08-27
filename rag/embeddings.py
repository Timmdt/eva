from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

try:
    import ollama
except ImportError:
    ollama = None


def normalize(vector: Iterable[float]) -> list[float]:
    values = [float(value) for value in vector]
    length = math.sqrt(sum(value * value for value in values))
    if not values or length == 0:
        raise ValueError("Embedding besitzt die Länge 0.")
    return [value / length for value in values]


class OllamaEmbeddingClient:
    """Version-tolerant Ollama embedding adapter with batch support."""

    def __init__(self, model: str = "nomic-embed-text") -> None:
        self.model = model
        self.dimension: int | None = None

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        clean = [text.strip() for text in texts]
        if not clean or any(not text for text in clean):
            raise ValueError("Leere Texte können nicht eingebettet werden.")
        if ollama is None:
            raise RuntimeError("Das Python-Paket 'ollama' ist nicht installiert.")

        embed = getattr(ollama, "embed", None)
        if callable(embed):
            response: Any = embed(model=self.model, input=clean)
            vectors = list(response.get("embeddings") or [])
        else:
            vectors = []
            for text in clean:
                response = ollama.embeddings(model=self.model, prompt=text)
                vectors.append(response.get("embedding") or [])

        if len(vectors) != len(clean):
            raise RuntimeError("Ollama lieferte nicht für jeden Text ein Embedding.")
        normalized = [normalize(vector) for vector in vectors]
        dimensions = {len(vector) for vector in normalized}
        if len(dimensions) != 1:
            raise RuntimeError("Ollama lieferte uneinheitliche Embedding-Dimensionen.")
        dimension = dimensions.pop()
        if self.dimension not in {None, dimension}:
            raise RuntimeError(
                f"Embedding-Dimension änderte sich von {self.dimension} auf {dimension}."
            )
        self.dimension = dimension
        return normalized

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def detect_dimension(self) -> int:
        if self.dimension is None:
            self.embed("EVA embedding dimension probe")
        assert self.dimension is not None
        return self.dimension
