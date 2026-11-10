"""Tests for JSONL evaluation datasets and Wikipedia snapshot validation."""

import json

import pytest

from wikirag.errors import ValidationError
from wikirag.evaluation.dataset import load_queries


def write_jsonl(tmp_path, records):
    path = tmp_path / "queries.jsonl"
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def write_snapshot(tmp_path, article_ids):
    path = tmp_path / "snapshot.jsonl"
    path.write_text(
        "\n".join(json.dumps({"article_id": article_id}) for article_id in article_ids),
        encoding="utf-8",
    )
    return path


def test_loads_jsonl_queries(tmp_path):
    path = write_jsonl(
        tmp_path,
        [
            {"query_id": "q1", "text": "What is MariaDB?", "relevant_article_ids": [101]},
            {
                "query_id": "q2",
                "text": "Which database articles are relevant?",
                "relevant_article_ids": [102, 103],
                "filters": {"topics": ["databases"]},
            },
        ],
    )

    queries = load_queries(path)

    assert [query.query_id for query in queries] == ["q1", "q2"]
    assert queries[1].relevant_article_ids == frozenset({102, 103})
    assert queries[1].filters.topics == ("databases",)


def test_rejects_malformed_jsonl(tmp_path):
    path = tmp_path / "queries.jsonl"
    path.write_text(
        '{"query_id":"q1","text":"Question","relevant_article_ids":[101]}\n{"query_id":\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="line 2"):
        load_queries(path)


def test_rejects_duplicate_jsonl_query_ids(tmp_path):
    path = write_jsonl(
        tmp_path,
        [
            {"query_id": "q1", "text": "First", "relevant_article_ids": [101]},
            {"query_id": "q1", "text": "Second", "relevant_article_ids": [102]},
        ],
    )

    with pytest.raises(ValidationError, match="unique"):
        load_queries(path)


@pytest.mark.parametrize(
    "filters",
    [
        {"min_length_chars": -1},
        {"article_ids": [True]},
        {"topics": [""]},
        {"max_distance": 3.0},
    ],
)
def test_rejects_invalid_filters(tmp_path, filters):
    path = write_jsonl(
        tmp_path,
        [
            {
                "query_id": "q1",
                "text": "Question",
                "relevant_article_ids": [101],
                "filters": filters,
            }
        ],
    )

    with pytest.raises(ValidationError):
        load_queries(path)


def test_validates_article_ids_against_snapshot(tmp_path):
    path = write_jsonl(
        tmp_path,
        [{"query_id": "q1", "text": "Question", "relevant_article_ids": [101, 102]}],
    )
    snapshot = write_snapshot(tmp_path, [101, 102, 103])

    assert len(load_queries(path, snapshot_path=snapshot)) == 1


def test_rejects_article_ids_missing_from_snapshot(tmp_path):
    path = write_jsonl(
        tmp_path,
        [{"query_id": "q1", "text": "Question", "relevant_article_ids": [101, 999]}],
    )
    snapshot = write_snapshot(tmp_path, [101, 102])

    with pytest.raises(ValidationError, match="missing from snapshot"):
        load_queries(path, snapshot_path=snapshot)


def test_rejects_invalid_jsonl_record(tmp_path):
    path = write_jsonl(tmp_path, [{"query_id": "q1", "text": "Question"}])

    with pytest.raises(ValidationError, match="relevant_article_ids"):
        load_queries(path)
