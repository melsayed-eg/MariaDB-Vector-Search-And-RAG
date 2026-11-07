"""Unit tests for the deterministic text cleaning."""

from __future__ import annotations

import pytest

from wikirag.errors import ValidationError
from wikirag.ingestion.cleaning import clean_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a  \t b", "a b"),
        ("a\u00a0b", "a b"),
        ("a\r\nb\rc", "a\nb\nc"),
        ("a  \n  b", "a\nb"),
        ("a\n   \nb", "a\n\nb"),
        ("a\n\n\n\nb", "a\n\nb"),
        ("a\n\nb", "a\n\nb"),
        ("\n\n a \n\n", "a"),
        ("a\u200bb\ufeffc\u00add\u2060e", "abcde"),
        ("e\u0301", "\u00e9"),
        ("Zürich ist schön", "Zürich ist schön"),
    ],
)
def test_cleaning_rules(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_zero_width_non_joiner_is_kept() -> None:
    assert clean_text("a\u200cb") == "a\u200cb"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t \n", "\u200b\ufeff"])
def test_empty_or_whitespace_only_gives_empty_text(raw: str) -> None:
    assert clean_text(raw) == ""


def test_cleaning_is_idempotent_and_deterministic() -> None:
    messy = "\ufeff Title \r\n\r\n\r\n\r\nFirst\u00a0 paragraph.  \n\tSecond\u200b line.\n\n\n"
    once = clean_text(messy)
    assert clean_text(messy) == once
    assert clean_text(once) == once


@pytest.mark.parametrize("value", [None, 5, b"bytes", ["text"]])
def test_non_string_raises(value: object) -> None:
    with pytest.raises(ValidationError, match="string"):
        clean_text(value)  # type: ignore[arg-type]


def test_clean_text_is_idempotent_when_an_invisible_character_splits_a_letter() -> None:
    from wikirag.ingestion.cleaning import clean_text

    once = clean_text("e\u00ad\u0301")
    assert once == "\u00e9"
    assert clean_text(once) == once


def test_clean_text_preserves_mathematical_comparisons() -> None:
    text = "For all inputs where x < y and z > 0, the condition holds."
    cleaned = clean_text(text)
    assert cleaned == "For all inputs where x < y and z > 0, the condition holds."


def test_clean_text_removes_html_and_citation_markers() -> None:
    raw = "<p>Text with <b>bold</b> and a reference[1] or citation[citation needed] and [edit].</p>"
    cleaned = clean_text(raw)
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "[1]" not in cleaned
    assert "[citation needed]" not in cleaned
    assert "[edit]" not in cleaned
    assert "Text with bold and a reference or citation and ." == cleaned
