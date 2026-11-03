"""Unit tests for extractive answer generation."""

import pytest

from wikirag.errors import ValidationError
from wikirag.models import ContextBundle, SearchHit
from wikirag.rag.generator import ExtractiveGenerator


@pytest.fixture
def context() -> ContextBundle:
    """Create a numbered context containing two source passages."""
    first = SearchHit(
        chunk_id=1,
        article_id=1,
        article_title="MariaDB",
        article_url="https://en.wikipedia.org/wiki/MariaDB",
        chunk_index=0,
        section_title="Overview",
        text="MariaDB is an open-source relational database. It supports SQL queries.",
        distance=0.1,
        score=0.9,
    )
    second = SearchHit(
        chunk_id=2,
        article_id=2,
        article_title="SQL",
        article_url="https://en.wikipedia.org/wiki/SQL",
        chunk_index=0,
        section_title="Overview",
        text="SQL is a language for managing relational databases.",
        distance=0.2,
        score=0.8,
    )
    return ContextBundle(
        text=(
            "[1] MariaDB — https://en.wikipedia.org/wiki/MariaDB\n"
            "Section: Overview\n"
            f"{first.text}\n\n"
            "[2] SQL — https://en.wikipedia.org/wiki/SQL\n"
            "Section: Overview\n"
            f"{second.text}"
        ),
        sources=(first, second),
        truncated=False,
    )


def test_generator_has_stable_name() -> None:
    assert ExtractiveGenerator().name == "extractive"


def test_generates_answer_with_citations(context: ContextBundle) -> None:
    answer = ExtractiveGenerator().generate("What is MariaDB?", context)

    assert "MariaDB is an open-source relational database." in answer
    assert "[1]" in answer


def test_can_select_sentence_from_second_source(context: ContextBundle) -> None:
    answer = ExtractiveGenerator().generate("What language manages databases?", context)

    assert "SQL is a language for managing relational databases." in answer
    assert "[2]" in answer


def test_falls_back_to_first_source_when_no_terms_overlap() -> None:
    hit = SearchHit(
        chunk_id=1,
        article_id=1,
        article_title="Example",
        article_url="https://example.com",
        chunk_index=0,
        section_title=None,
        text="A completely unrelated passage.",
        distance=0.1,
        score=0.9,
    )
    context = ContextBundle(
        text="[1] Example — https://example.com\nA completely unrelated passage.",
        sources=(hit,),
        truncated=False,
    )

    answer = ExtractiveGenerator().generate("quantum zebras?", context)

    assert answer == "A completely unrelated passage. [1]"


@pytest.mark.parametrize("question", ["", "  ", None, 123])
def test_rejects_invalid_question(context: ContextBundle, question) -> None:
    with pytest.raises(ValidationError):
        ExtractiveGenerator().generate(question, context)


def test_rejects_invalid_context() -> None:
    with pytest.raises(ValidationError):
        ExtractiveGenerator().generate("What is MariaDB?", None)


def test_rejects_empty_context() -> None:
    empty = ContextBundle(text="", sources=(), truncated=False)

    with pytest.raises(ValidationError):
        ExtractiveGenerator().generate("What is MariaDB?", empty)
