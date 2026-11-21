"""Local Ollama client for batch text embeddings."""

import math
import os
from collections.abc import Sequence

from .ollama_client import OllamaClient, OllamaError


class OllamaEmbeddingClient:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self.model = model or os.environ.get("OLLAMA_EMBEDDING_MODEL", "embeddinggemma")
        self._client = OllamaClient(base_url=base_url, model=self.model)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding input must contain non-empty strings")
        response = self._client._request("/api/embed", {"model": self.model, "input": list(texts)})
        vectors = response.get("embeddings") if isinstance(response, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise OllamaError("Ollama embedding response vector count did not match input count")
        normalized: list[list[float]] = []
        dimension: int | None = None
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise OllamaError("Ollama returned an empty or invalid embedding vector")
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise OllamaError("Ollama embedding contained a non-numeric value") from exc
            if not all(math.isfinite(value) for value in values):
                raise OllamaError("Ollama embedding contained a non-finite value")
            if dimension is not None and len(values) != dimension:
                raise OllamaError("Ollama returned embedding vectors with inconsistent dimensions")
            dimension = len(values)
            normalized.append(values)
        return normalized
