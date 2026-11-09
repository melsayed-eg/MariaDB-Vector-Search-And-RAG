"""Unit tests for RAG context construction."""

from dataclasses import FrozenInstanceError

import pytest

from wikirag.errors import ValidationError
from wikirag.models import SearchHit
from wikirag.rag.context import build_context


def make_hit(
    chunk_id: int = 1,
    *,
    title: str = "MariaDB",
    url: str = "https://en.wikipedia.org/wiki/MariaDB",
    section: str | None = "Overview",
    text: str = "MariaDB is an open-source relational database.",
) -> SearchHit:
    """Create a search hit for context tests."""
    return SearchHit(
        chunk_id=chunk_id,
        article_id=chunk_id,
        article_title=title,
        article_url=url,
        chunk_index=0,
        section_title=section,
        text=text,
        distance=0.1,
        score=0.9,
    )


def test_builds_numbered_context_in_retrieval_order() -> None:
    first = make_hit(1, title="MariaDB", text="First source.")
    second = make_hit(
        2,
        title="SQL",
        section="History",
        text="Second source.",
    )

    result = build_context([first, second])

    assert result.sources == (first, second)
    assert "[1] MariaDB — https://en.wikipedia.org/wiki/MariaDB" in result.text
    assert "Section: Overview\nFirst source." in result.text
    assert "[2] SQL — https://en.wikipedia.org/wiki/MariaDB" in result.text
    assert "Section: History\nSecond source." in result.text
    assert result.text.index("First source.") < result.text.index("Second source.")
    assert result.truncated is False


def test_deduplicates_chunk_ids_preserving_first_occurrence() -> None:
    first = make_hit(1, text="Original content.")
    duplicate = make_hit(1, text="Duplicate content.")
    second = make_hit(2, title="SQL", text="Other content.")

    result = build_context([first, duplicate, second])

    assert result.sources == (first, second)
    assert "Original content." in result.text
    assert "Duplicate content." not in result.text
    assert "[2] SQL" in result.text


def test_does_not_split_chunks_when_context_limit_is_reached() -> None:
    first = make_hit(1, text="A short chunk.")
    second = make_hit(2, text="B" * 100)

    first_only = build_context([first])
    result = build_context([first, second], max_chars=len(first_only.text))

    assert result.sources == (first,)
    assert result.text == first_only.text
    assert result.truncated is True
    assert len(result.text) <= len(first_only.text)


def test_marks_truncated_when_first_chunk_does_not_fit() -> None:
    result = build_context([make_hit(text="Long content.")], max_chars=1)

    assert result.text == ""
    assert result.sources == ()
    assert result.truncated is True


def test_empty_hits_produce_empty_context() -> None:
    result = build_context([])

    assert result.text == ""
    assert result.sources == ()
    assert result.truncated is False


def test_omits_section_line_when_section_is_missing() -> None:
    result = build_context([make_hit(section=None)])

    assert "Section:" not in result.text


@pytest.mark.parametrize("max_chars", [0, -1, True, 1.5, "100", None])
def test_rejects_invalid_max_chars(max_chars) -> None:
    with pytest.raises(ValidationError):
        build_context([], max_chars=max_chars)


def test_context_bundle_is_immutable() -> None:
    result = build_context([make_hit()])

    with pytest.raises(FrozenInstanceError):
        result.text = "changed"
