"""Unit tests for the evaluation dataset loader."""

import json

import pytest

from wikirag.errors import ValidationError
from wikirag.evaluation.dataset import load_queries
from wikirag.models import SearchFilters


def write_dataset(tmp_path, data) -> object:
    """Write JSON data to a temporary dataset file."""
    path = tmp_path / "queries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_loads_valid_query(tmp_path) -> None:
    path = write_dataset(
        tmp_path,
        [
            {
                "query_id": "q1",
                "text": "What is MariaDB?",
                "relevant_article_ids": [101, 102],
                "notes": "Database question",
            }
        ],
    )

    queries = load_queries(path)

    assert len(queries) == 1
    assert queries[0].query_id == "q1"
    assert queries[0].text == "What is MariaDB?"
    assert queries[0].relevant_article_ids == frozenset({101, 102})
    assert queries[0].notes == "Database question"
    assert queries[0].filters is None


def test_loads_filters_and_deduplicates_relevant_ids(tmp_path) -> None:
    path = write_dataset(
        tmp_path,
        [
            {
                "query_id": "q1",
                "text": "What is MariaDB?",
                "relevant_article_ids": [101, 101],
                "filters": {
                    "topics": ["databases"],
                    "article_ids": [101],
                    "max_distance": 0.5,
                },
            }
        ],
    )

    query = load_queries(path)[0]

    assert query.relevant_article_ids == frozenset({101})
    assert query.filters == SearchFilters(
        topics=("databases",),
        article_ids=(101,),
        max_distance=0.5,
    )


def test_loads_naive_iso_datetime_filter(tmp_path) -> None:
    path = write_dataset(
        tmp_path,
        [
            {
                "query_id": "q1",
                "text": "Recent articles",
                "relevant_article_ids": [101],
                "filters": {"edited_since": "2025-01-01T12:30:00"},
            }
        ],
    )

    assert load_queries(path)[0].filters.edited_since.isoformat() == ("2025-01-01T12:30:00")


@pytest.mark.parametrize(
    "data",
    [
        {},
        [],
        [{"query_id": "", "text": "Question", "relevant_article_ids": [1]}],
        [{"query_id": "q1", "text": "", "relevant_article_ids": [1]}],
        [{"query_id": "q1", "text": "Question", "relevant_article_ids": []}],
        [{"query_id": "q1", "text": "Question", "relevant_article_ids": [0]}],
        [{"query_id": "q1", "text": "Question", "relevant_article_ids": [True]}],
        [
            {"query_id": "q1", "text": "Question", "relevant_article_ids": [1]},
            {"query_id": "q1", "text": "Another question", "relevant_article_ids": [2]},
        ],
        [
            {
                "query_id": "q1",
                "text": "Question",
                "relevant_article_ids": [1],
                "filters": {"unknown_filter": "value"},
            }
        ],
        [
            {
                "query_id": "q1",
                "text": "Question",
                "relevant_article_ids": [1],
                "filters": {"edited_since": "not-a-date"},
            }
        ],
    ],
)
def test_rejects_invalid_datasets(tmp_path, data) -> None:
    path = write_dataset(tmp_path, data)

    with pytest.raises(ValidationError):
        load_queries(path)


def test_rejects_invalid_json(tmp_path) -> None:
    path = tmp_path / "queries.json"
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValidationError, match="valid JSON"):
        load_queries(path)


def test_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(ValidationError, match="Could not read"):
        load_queries(tmp_path / "missing.json")


def test_rejects_timezone_aware_datetime(tmp_path) -> None:
    path = write_dataset(
        tmp_path,
        [
            {
                "query_id": "q1",
                "text": "Recent articles",
                "relevant_article_ids": [101],
                "filters": {"edited_since": "2025-01-01T12:30:00+01:00"},
            }
        ],
    )

    with pytest.raises(ValidationError, match="naive UTC"):
        load_queries(path)
