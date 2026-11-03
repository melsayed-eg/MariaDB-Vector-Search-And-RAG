"""Unit tests for fetch_article parameter validation and malformed pages."""

from datetime import datetime

import pytest

from wikirag.errors import ValidationError
from wikirag.ingestion.wikipedia import fetch_article, parse_article_page


@pytest.mark.parametrize("max_requests", [0, -1, True, 2.5, "3", None])
def test_invalid_max_requests_rejected(max_requests: object) -> None:
    with pytest.raises(ValidationError, match="max_requests"):
        fetch_article("Sorting algorithm", max_requests=max_requests)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout_s", [0, -1, True, float("nan"), float("inf"), "5", None])
def test_invalid_timeout_rejected(timeout_s: object) -> None:
    with pytest.raises(ValidationError, match="timeout_s"):
        fetch_article("Sorting algorithm", timeout_s=timeout_s)  # type: ignore[arg-type]


@pytest.mark.parametrize("title", [None, 5, ["a"], ""])
def test_invalid_title_rejected(title: object) -> None:
    with pytest.raises(ValidationError, match="title"):
        fetch_article(title)  # type: ignore[arg-type]


@pytest.mark.parametrize("revisions", [["not a dict"], "text", [None], 5])
def test_malformed_revisions_raise_validation_error(revisions: object) -> None:
    page = {"title": "X", "pageid": 1, "revisions": revisions, "extract": "text"}
    with pytest.raises(ValidationError):
        parse_article_page(page, fetched_at=datetime(2026, 1, 1))
