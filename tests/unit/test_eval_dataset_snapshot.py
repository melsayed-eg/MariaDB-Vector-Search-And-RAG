"""Validate the committed Wikipedia evaluation dataset."""

from pathlib import Path

import pytest

from wikirag.errors import ValidationError
from wikirag.evaluation.dataset import load_queries
from wikirag.evaluation.run_eval import run_evaluation
from wikirag.models import EvalQuery

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/eval/queries.jsonl"
SNAPSHOT = ROOT / "data/snapshot/wikipedia_snapshot.jsonl"


def test_committed_dataset_matches_snapshot():
    queries = load_queries(DATASET, snapshot_path=SNAPSHOT)

    assert len(queries) == 40
    assert all(isinstance(query, EvalQuery) for query in queries)
    assert len({query.query_id for query in queries}) == 40
    assert sum(query.filters is None for query in queries) == 25
    assert sum(query.filters is not None for query in queries) == 15
    assert all(1 <= len(query.relevant_article_ids) <= 5 for query in queries)
    assert all(
        query.filters is not None and not query.filters.is_empty()
        for query in queries
        if query.query_id.startswith("hyb_")
    )


def test_runner_rejects_chunk_pool_smaller_than_k():
    queries = load_queries(DATASET, snapshot_path=SNAPSHOT)

    with pytest.raises(ValidationError, match=r"chunk_pool must be at least max\(ks\)"):
        run_evaluation(
            queries,
            retriever=None,
            ks=(1, 3, 5, 10),
            chunk_pool=3,
        )
