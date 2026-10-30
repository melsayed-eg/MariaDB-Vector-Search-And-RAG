"""Embedding generation using sentence-transformers."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol

import numpy as np
from sentence_transformers import SentenceTransformer

from wikirag.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME
from wikirag.errors import EmbeddingDimensionError, ValidationError


class Embedder(Protocol):
    """Protocol for embedding text documents and queries."""

    @property
    def model_name(self) -> str:
        """Name of the embedding model."""
        ...

    @property
    def dim(self) -> int:
        """Dimension of the embedding vector."""
        ...

    def embed_texts(self, texts: Sequence[str], *, batch_size: int = 32) -> list[list[float]]:
        """Embed a list of strings into normalized float vectors."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string into a normalized float vector."""
        ...


class SentenceTransformerEmbedder:
    """Embedder using sentence-transformers with L2 normalization."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME) -> None:
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._dim = EMBEDDING_DIM

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def embed_texts(self, texts: Sequence[str], *, batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []

        for i, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise ValidationError(f"Text at index {i} must not be blank")

        embeddings = self._model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        vectors: list[list[float]] = []
        for vec in embeddings:
            vec_list = [float(x) for x in vec]
            if len(vec_list) != self._dim or not np.all(np.isfinite(vec)):
                raise EmbeddingDimensionError(f"Expected {self._dim} dimensions")
            vectors.append(vec_list)

        return vectors

    def embed_query(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("Query text must not be blank")
        return self.embed_texts([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Return a cached process-wide Embedder instance."""
    return SentenceTransformerEmbedder()
    