"""Tests for embedding functionality."""

import math
from importlib.util import find_spec

import pytest

from wikirag.config import EMBEDDING_DIM, EMBEDDING_MODEL_NAME
from wikirag.embeddings import SentenceTransformerEmbedder
from wikirag.errors import ValidationError


@pytest.fixture(scope="module")
def embedder() -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder()


def test_embedder_properties(embedder: SentenceTransformerEmbedder) -> None:
    assert embedder.model_name == EMBEDDING_MODEL_NAME
    assert embedder.dim == EMBEDDING_DIM


def test_embed_empty_list_returns_empty(embedder: SentenceTransformerEmbedder) -> None:
    assert embedder.embed_texts([]) == []


def test_embed_blank_text_raises_validation_error(embedder: SentenceTransformerEmbedder) -> None:
    with pytest.raises(ValidationError):
        embedder.embed_texts(["valid text", "   "])

    with pytest.raises(ValidationError):
        embedder.embed_query("   ")


def test_embed_produces_normalized_vectors(embedder: SentenceTransformerEmbedder) -> None:
    vectors = embedder.embed_texts(["MariaDB vector search", "Relational database"])
    assert len(vectors) == 2
    for vec in vectors:
        assert len(vec) == EMBEDDING_DIM
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-4


def test_embed_determinism(embedder: SentenceTransformerEmbedder) -> None:
    text = "Deterministic testing"
    v1 = embedder.embed_query(text)
    v2 = embedder.embed_query(text)
    assert v1 == v2


pytestmark = pytest.mark.skipif(
    find_spec("sentence_transformers") is None,
    reason="sentence-transformers is not installed",
)


def test_wrong_vector_count_is_rejected() -> None:
    """A model that returns too few vectors raises EmbeddingDimensionError."""
    from wikirag.embeddings import SentenceTransformerEmbedder
    from wikirag.errors import EmbeddingDimensionError

    embedder = SentenceTransformerEmbedder.__new__(SentenceTransformerEmbedder)
    embedder._dim = 384

    class OneVectorModel:
        def encode(self, texts, **kwargs):  # type: ignore[no-untyped-def]
            return [[1.0] + [0.0] * 383]

    embedder._model = OneVectorModel()
    with pytest.raises(EmbeddingDimensionError):
        embedder.embed_texts(["a", "b"])
