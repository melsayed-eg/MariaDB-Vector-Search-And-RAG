"""Verify that the embedding factory respects application configuration."""

from types import SimpleNamespace
from unittest.mock import Mock

from wikirag import embeddings


def test_get_embedder_uses_configured_model(
    monkeypatch,
) -> None:
    """Verify that the configured model is loaded and cached.

    Args:
        monkeypatch: Pytest fixture for replacing dependencies.

    Returns:
        None: Assertions verify model selection and caching.
    """
    settings = SimpleNamespace(
        embedding_model="example/test-384-model",
    )

    fake_embedder = object()
    model_factory = Mock(return_value=fake_embedder)

    monkeypatch.setattr(
        embeddings,
        "load_settings",
        Mock(return_value=settings),
    )
    monkeypatch.setattr(
        embeddings,
        "SentenceTransformerEmbedder",
        model_factory,
    )

    embeddings.get_embedder.cache_clear()

    try:
        first = embeddings.get_embedder()
        second = embeddings.get_embedder()

        assert first is fake_embedder
        assert second is fake_embedder

        model_factory.assert_called_once_with(
            model_name="example/test-384-model",
        )
    finally:
        # Do not leave the mocked model cached for other tests.
        embeddings.get_embedder.cache_clear()
