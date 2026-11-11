"""Tests for independent hybrid filter-compliance verification."""

from dataclasses import replace
from datetime import datetime
from unittest.mock import Mock

import pytest

from wikirag.evaluation.compliance import check_filter_compliance
from wikirag.models import ArticleRecord, RetrievalResult, SearchFilters, SearchHit


def make_article(article_id=10, **changes):
    """Build an article with known metadata."""
    article = ArticleRecord(
        article_id=article_id,
        title="Example",
        url="https://en.wikipedia.org/wiki/Example",
        revision_id=1,
        fingerprint="a" * 64,
        revised_at=datetime(2025, 1, 1),
        length_chars=1000,
        fetched_at=datetime(2025, 1, 2),
        topic="Databases",
        categories=("Computer science",),
        linked_titles=(),
    )
    return replace(article, **changes)


def make_hit(article_id=10, distance=0.2):
    """Build a retrieval hit with known distance."""
    return SearchHit(
        chunk_id=article_id * 10,
        article_id=article_id,
        article_title="Example",
        article_url="https://en.wikipedia.org/wiki/Example",
        chunk_index=0,
        section_title=None,
        text="Example chunk",
        distance=distance,
        score=1.0 - distance,
    )


def make_result(*hits):
    """Build a hybrid retrieval result."""
    return RetrievalResult(
        query="Example question",
        mode="hybrid",
        top_k=30,
        filters=None,
        hits=tuple(hits),
        embed_ms=1.0,
        search_ms=2.0,
        latency_ms=3.0,
    )


def test_all_constraints_pass():
    """Accept a hit satisfying multiple simultaneous constraints."""
    repo = Mock()
    repo.get_article.return_value = make_article()
    repo.get_linked_articles.return_value = [make_article()]

    filters = SearchFilters(
        topics=("DATABASES",),
        categories=("computer SCIENCE",),
        article_ids=(10,),
        exclude_article_ids=(20,),
        min_length_chars=999,
        edited_since=datetime(2024, 1, 1),
        linked_from_article_id=5,
        max_distance=0.2,
    )

    result = check_filter_compliance(make_result(make_hit()), filters, repo)

    assert result["returned_hits"] == 1
    assert result["compliant_hits"] == 1
    assert result["violating_hits"] == 0
    assert result["compliance_rate"] == 1.0
    assert result["violations"] == []


def test_multiple_violations():
    """Identify all failing constraints for a noncompliant hit."""
    repo = Mock()
    repo.get_article.return_value = make_article()
    repo.get_linked_articles.return_value = []

    filters = SearchFilters(
        topics=("algorithms",),
        categories=("Physics",),
        article_ids=(99,),
        exclude_article_ids=(10,),
        min_length_chars=1000,
        edited_since=datetime(2026, 1, 1),
        linked_from_article_id=5,
        max_distance=0.1,
    )

    result = check_filter_compliance(make_result(make_hit()), filters, repo)

    assert result["violating_hits"] == 1
    assert result["compliance_rate"] == 0.0
    assert set(result["violations"][0]["failed_constraints"]) == {
        "topics",
        "categories",
        "article_ids",
        "exclude_article_ids",
        "min_length_chars",
        "edited_since",
        "linked_from_article_id",
        "max_distance",
    }


def test_empty_results():
    """Report empty results separately without dividing by zero."""
    repo = Mock()

    result = check_filter_compliance(
        make_result(),
        SearchFilters(topics=("databases",)),
        repo,
    )

    assert result["returned_hits"] == 0
    assert result["compliant_hits"] == 0
    assert result["violating_hits"] == 0
    assert result["compliance_rate"] == 1.0
    assert result["empty_result"] is True
    repo.get_article.assert_not_called()


def test_missing_article():
    """Treat a hit with no corresponding stored article as a violation."""
    repo = Mock()
    repo.get_article.return_value = None

    result = check_filter_compliance(
        make_result(make_hit()),
        SearchFilters(topics=("databases",)),
        repo,
    )

    assert result["violating_hits"] == 1
    assert result["violations"][0]["failed_constraints"] == ["article_missing"]


def test_mixed_compliance():
    """Count compliant and violating hits independently."""
    repo = Mock()
    repo.get_article.side_effect = [
        make_article(10),
        make_article(20, topic="Algorithms"),
    ]

    result = check_filter_compliance(
        make_result(make_hit(10), make_hit(20)),
        SearchFilters(topics=("databases",)),
        repo,
    )

    assert result["returned_hits"] == 2
    assert result["compliant_hits"] == 1
    assert result["violating_hits"] == 1
    assert result["compliance_rate"] == pytest.approx(0.5)
