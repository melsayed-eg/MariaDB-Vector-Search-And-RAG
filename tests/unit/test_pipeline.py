"""Unit tests for the RAG pipeline."""

from unittest.mock import Mock

import pytest

from wikirag.errors import WikiRagError
from wikirag.models import RetrievalResult, SearchHit
from wikirag.rag.generator import ExtractiveGenerator
from wikirag.rag.pipeline import answer_question


@pytest.fixture
def hit() -> SearchHit:
    """Return one representative retrieved chunk."""
    return SearchHit(
        chunk_id=1,
        article_id=1,
        article_title="MariaDB",
        article_url="https://en.wikipedia.org/wiki/MariaDB",
        chunk_index=0,
        section_title="Overview",
        text="MariaDB is an open-source relational database.",
        distance=0.1,
        score=0.9,
    )


def make_retrieval(hits: tuple[SearchHit, ...]) -> RetrievalResult:
    """Build a retrieval result for pipeline tests."""
    return RetrievalResult(
        query="What is MariaDB?",
        mode="semantic",
        top_k=5,
        filters=None,
        hits=hits,
        embed_ms=1.0,
        search_ms=2.0,
        latency_ms=3.0,
    )


def test_pipeline_returns_grounded_answer(hit: SearchHit) -> None:
    retriever = Mock()
    retriever.retrieve.return_value = make_retrieval((hit,))

    result = answer_question(
        "What is MariaDB?",
        retriever,
        ExtractiveGenerator(),
    )

    assert "MariaDB is an open-source relational database." in result.answer
    assert "[1]" in result.answer
    assert result.context.sources == (hit,)
    assert result.generator_name == "extractive"
    assert result.latency_ms >= 0


def test_pipeline_skips_generator_when_no_hits() -> None:
    retriever = Mock()
    retriever.retrieve.return_value = make_retrieval(())
    generator = Mock()

    result = answer_question("What is MariaDB?", retriever, generator)

    assert "don't have enough information" in result.answer
    generator.generate.assert_not_called()
    assert result.context.sources == ()


def test_pipeline_wraps_generator_failure(hit: SearchHit) -> None:
    retriever = Mock()
    retriever.retrieve.return_value = make_retrieval((hit,))
    generator = Mock()
    generator.generate.side_effect = RuntimeError("generation failed")

    with pytest.raises(WikiRagError, match="Answer generation failed"):
        answer_question("What is MariaDB?", retriever, generator)


def test_pipeline_rejects_answer_without_citations(hit: SearchHit) -> None:
    retriever = Mock()
    retriever.retrieve.return_value = make_retrieval((hit,))
    generator = Mock()
    generator.generate.return_value = "MariaDB is a database."

    with pytest.raises(WikiRagError, match="must cite"):
        answer_question("What is MariaDB?", retriever, generator)


def test_pipeline_rejects_invalid_citation_numbers(hit: SearchHit) -> None:
    retriever = Mock()
    retriever.retrieve.return_value = make_retrieval((hit,))
    generator = Mock()
    generator.generate.return_value = "MariaDB is a database. [2]"

    with pytest.raises(WikiRagError, match="must cite"):
        answer_question("What is MariaDB?", retriever, generator)
