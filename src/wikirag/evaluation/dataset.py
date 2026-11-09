"""Load and validate retrieval evaluation questions from JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wikirag.errors import ValidationError
from wikirag.models import EvalQuery, SearchFilters


def _parse_filters(value: Any) -> SearchFilters | None:
    """Parse optional search filters from a JSON object."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValidationError("filters must be a JSON object or null")

    allowed = {
        "topics",
        "categories",
        "article_ids",
        "exclude_article_ids",
        "min_length_chars",
        "edited_since",
        "linked_from_article_id",
        "max_distance",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValidationError(f"Unknown filter fields: {sorted(unknown)}")

    parsed = dict(value)

    for field in ("topics", "categories", "article_ids", "exclude_article_ids"):
        if field in parsed:
            if not isinstance(parsed[field], list):
                raise ValidationError(f"filters.{field} must be a JSON array")
            parsed[field] = tuple(parsed[field])

    if "edited_since" in parsed:
        timestamp = parsed["edited_since"]
        if not isinstance(timestamp, str):
            raise ValidationError("filters.edited_since must be an ISO datetime")
        from datetime import datetime

        try:
            parsed["edited_since"] = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValidationError("filters.edited_since must be an ISO datetime") from exc

        if parsed["edited_since"].tzinfo is not None:
            raise ValidationError("filters.edited_since must be a naive UTC datetime")

    try:
        return SearchFilters(**parsed)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid search filters: {exc}") from exc


def _parse_query(item: Any, index: int) -> EvalQuery:
    """Parse one evaluation query object."""
    if not isinstance(item, dict):
        raise ValidationError(f"Query at index {index} must be a JSON object")

    query_id = item.get("query_id")
    text = item.get("text")
    relevant = item.get("relevant_article_ids")
    notes = item.get("notes", "")

    if not isinstance(query_id, str) or not query_id.strip():
        raise ValidationError(f"Query at index {index} needs a non-empty query_id")
    if not isinstance(text, str) or not text.strip():
        raise ValidationError(f"Query {query_id!r} needs non-empty text")
    if (
        not isinstance(relevant, list)
        or not relevant
        or any(
            not isinstance(article_id, int) or isinstance(article_id, bool) or article_id <= 0
            for article_id in relevant
        )
    ):
        raise ValidationError(f"Query {query_id!r} needs positive integer relevant_article_ids")
    if not isinstance(notes, str):
        raise ValidationError(f"Query {query_id!r}: notes must be a string")

    filters = _parse_filters(item.get("filters"))

    return EvalQuery(
        query_id=query_id,
        text=text,
        relevant_article_ids=frozenset(relevant),
        filters=filters,
        notes=notes,
    )


def load_queries(path: Path) -> list[EvalQuery]:
    """Load evaluation queries from a JSON file.

    The file must contain a JSON array of objects with ``query_id``,
    ``text``, and ``relevant_article_ids`` fields. Optional ``filters`` and
    ``notes`` fields are supported.

    Args:
        path: Path to the JSON dataset.

    Returns:
        Parsed evaluation queries in file order.

    Raises:
        ValidationError: If the file cannot be read or its contents are invalid.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"Could not read evaluation dataset: {path}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError("Evaluation dataset must contain valid JSON") from exc

    if not isinstance(data, list) or not data:
        raise ValidationError("Evaluation dataset must be a non-empty JSON array")

    queries = [_parse_query(item, index) for index, item in enumerate(data)]

    query_ids = [query.query_id for query in queries]
    if len(query_ids) != len(set(query_ids)):
        raise ValidationError("Evaluation query_id values must be unique")

    return queries
