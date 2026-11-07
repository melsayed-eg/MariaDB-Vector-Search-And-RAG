"""Embedding generation using sentence-transformers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol

from sentence_transformers import SentenceTransformer

from wikirag.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME
from wikirag.errors import EmbeddingDimensionError, ValidationError, WikiRagError

# tolerance for "the vector has length 1"
NORM_TOLERANCE = 1e-3


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
        """Load the sentence-transformer model.

        Args:
            model_name: Name of the sentence-transformers model to load.

        Raises:
            ValidationError: If the model name is blank.
            WikiRagError: If the model cannot be loaded.
        """
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValidationError("model_name must be a non-empty string")
        self._model_name = model_name.strip()
        try:
            self._model = SentenceTransformer(self._model_name, device="cpu")
        except Exception as error:
            raise WikiRagError(f"Could not load embedding model {self._model_name!r}") from error
        self._dim = EMBEDDING_DIM

    @property
    def model_name(self) -> str:
        """Return the name of the loaded model."""
        return self._model_name

    @property
    def dim(self) -> int:
        """Return the number of dimensions of every vector."""
        return self._dim

    def _check_vector(self, vector: list[float]) -> None:
        """Check one vector for length, finite values and unit norm.

        Args:
            vector: The embedding to check.

        Raises:
            EmbeddingDimensionError: If the vector is malformed.
        """
        if len(vector) != self._dim:
            raise EmbeddingDimensionError(f"Expected {self._dim} dimensions, got {len(vector)}")
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingDimensionError("Embedding contains non-finite values")
        norm = math.sqrt(math.fsum(value * value for value in vector))
        if abs(norm - 1.0) > NORM_TOLERANCE:
            raise EmbeddingDimensionError(f"Embedding is not normalized (norm {norm:.4f})")

    def embed_texts(self, texts: Sequence[str], *, batch_size: int = 32) -> list[list[float]]:
        """Embed texts into normalized vectors, keeping the input order.

        Args:
            texts: Non-blank strings to embed.
            batch_size: Number of texts the model processes at once.

        Returns:
            One vector per text; an empty list for an empty input.

        Raises:
            ValidationError: If texts is not a sequence of non-blank strings or
                batch_size is not a positive integer.
            EmbeddingDimensionError: If the model returns a malformed vector.
            WikiRagError: If the model fails while encoding.
        """
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise ValidationError("texts must be a sequence of strings")
        if type(batch_size) is not int or batch_size < 1:
            raise ValidationError("batch_size must be a positive integer")
        if not texts:
            return []
        for index, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise ValidationError(f"Text at index {index} must not be blank")

        try:
            embeddings = self._model.encode(
                list(texts),
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as error:
            raise WikiRagError("Embedding model failed while encoding") from error

        vectors = [[float(value) for value in row] for row in embeddings]
        for vector in vectors:
            self._check_vector(vector)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed one query string.

        Args:
            text: Non-blank query text.

        Returns:
            The normalized embedding.

        Raises:
            ValidationError: If the text is blank.
        """
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("Query text must not be blank")
        return self.embed_texts([text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Return a cached process-wide embedder.

    Returns:
        The shared SentenceTransformerEmbedder instance.
    """
    return SentenceTransformerEmbedder()
