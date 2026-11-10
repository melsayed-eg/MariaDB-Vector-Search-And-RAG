"""Load and validate retrieval evaluation questions from JSON or JSONL."""

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
        filters = SearchFilters(**parsed)
        filters.validate()
        return filters
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


def load_queries(path: Path, *, snapshot_path: Path | None = None) -> list[EvalQuery]:
    """Load JSON or JSONL evaluation queries and optionally validate snapshot IDs."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationError(f"Could not read evaluation dataset: {path}") from exc

    if path.suffix.lower() == ".jsonl":
        records = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"Invalid JSONL at line {line_number}: {exc.msg}") from exc
        if not records:
            raise ValidationError("Evaluation dataset must not be empty")
    else:
        try:
            records = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValidationError("Evaluation dataset must contain valid JSON") from exc
        if not isinstance(records, list) or not records:
            raise ValidationError("Evaluation dataset must be a non-empty JSON array")

    queries = [_parse_query(item, index) for index, item in enumerate(records)]

    query_ids = [query.query_id for query in queries]
    if len(query_ids) != len(set(query_ids)):
        raise ValidationError("Evaluation query_id values must be unique")

    if snapshot_path is not None:
        try:
            snapshot_lines = snapshot_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValidationError(f"Could not read Wikipedia snapshot: {snapshot_path}") from exc

        snapshot_ids = set()
        for line_number, line in enumerate(snapshot_lines, start=1):
            if not line.strip():
                continue
            try:
                article = json.loads(line)
                article_id = article["article_id"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValidationError(
                    f"Invalid Wikipedia snapshot record at line {line_number}"
                ) from exc
            if type(article_id) is not int or article_id <= 0:
                raise ValidationError(f"Invalid Wikipedia article ID at line {line_number}")
            snapshot_ids.add(article_id)

        if not snapshot_ids:
            raise ValidationError("Wikipedia snapshot must not be empty")

        for query in queries:
            missing = query.relevant_article_ids - snapshot_ids
            if missing:
                raise ValidationError(
                    f"Query {query.query_id!r} references articles "
                    f"missing from snapshot: {sorted(missing)}"
                )

    return queries
