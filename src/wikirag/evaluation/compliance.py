"""Independently verify hybrid retrieval constraints against stored metadata."""

from __future__ import annotations

from typing import Protocol

from wikirag.models import ArticleRecord, RetrievalResult, SearchFilters


class ComplianceRepository(Protocol):
    """Repository operations needed to verify retrieved results."""

    def get_article(self, article_id: int) -> ArticleRecord | None:
        """Fetch authoritative stored article metadata."""
        ...

    def get_linked_articles(self, article_id: int) -> list[ArticleRecord]:
        """Fetch resolved outgoing article links."""
        ...


def check_filter_compliance(
    result: RetrievalResult,
    filters: SearchFilters,
    repo: ComplianceRepository,
) -> dict[str, object]:
    """Verify each returned chunk against every active hybrid constraint.

    Args:
        result: Retrieval output containing chunk hits and distances.
        filters: Constraints that the hybrid query was expected to apply.
        repo: Repository providing independently fetched article metadata.

    Returns:
        Counts, compliance rate, and details of any violations. Empty
        result sets have a compliance rate of 1.0 by convention.

    Raises:
        ValidationError: If the supplied filters are invalid.
    """
    filters.validate()

    allowed_topics = {value.casefold() for value in filters.topics}
    allowed_categories = {value.casefold() for value in filters.categories}

    linked_ids: set[int] | None = None
    if filters.linked_from_article_id is not None:
        linked_ids = {
            article.article_id
            for article in repo.get_linked_articles(filters.linked_from_article_id)
        }

    articles: dict[int, ArticleRecord | None] = {}
    violations: list[dict[str, object]] = []

    for hit in result.hits:
        if hit.article_id not in articles:
            articles[hit.article_id] = repo.get_article(hit.article_id)

        article = articles[hit.article_id]
        failed: list[str] = []

        if article is None:
            failed.append("article_missing")
        else:
            if allowed_topics and (
                article.topic is None or article.topic.casefold() not in allowed_topics
            ):
                failed.append("topics")

            if allowed_categories and not (
                {category.casefold() for category in article.categories} & allowed_categories
            ):
                failed.append("categories")

            if filters.article_ids and article.article_id not in filters.article_ids:
                failed.append("article_ids")

            if article.article_id in filters.exclude_article_ids:
                failed.append("exclude_article_ids")

            if (
                filters.min_length_chars is not None
                and article.length_chars <= filters.min_length_chars
            ):
                failed.append("min_length_chars")

            if filters.edited_since is not None and article.revised_at < filters.edited_since:
                failed.append("edited_since")

            if linked_ids is not None and article.article_id not in linked_ids:
                failed.append("linked_from_article_id")

        if filters.max_distance is not None and hit.distance > filters.max_distance:
            failed.append("max_distance")

        if failed:
            violations.append(
                {
                    "chunk_id": hit.chunk_id,
                    "article_id": hit.article_id,
                    "failed_constraints": failed,
                }
            )

    returned = len(result.hits)
    failed_count = len(violations)
    passed = returned - failed_count

    return {
        "returned_hits": returned,
        "compliant_hits": passed,
        "violating_hits": failed_count,
        "compliance_rate": passed / returned if returned else 1.0,
        "empty_result": returned == 0,
        "violations": violations,
    }
