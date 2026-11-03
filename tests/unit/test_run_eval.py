"""Unit tests for the retrieval evaluation runner."""


import pytest

from wikirag.errors import ValidationError
from wikirag.evaluation.run_eval import run_evaluation
from wikirag.models import (
    EvalQuery,
    RetrievalResult,
    SearchFilters,
    SearchHit,
)


def _hit(chunk_id: int, article_id: int) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        article_id=article_id,
        article_title=f"Article {article_id}",
        article_url=f"https://example.com/{article_id}",
        chunk_index=chunk_id,
        section_title=None,
        text=f"Text for article {article_id}",
        distance=0.1,
        score=0.9,
    )


class FakeRetriever:
    def __init__(self) -> None:
        self.calls = []

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        mode: str = "semantic",
        filters: SearchFilters | None = None,
    ) -> RetrievalResult:
        self.calls.append((query, top_k, mode, filters))

        if query == "filtered question":
            hits = (_hit(1, 10), _hit(2, 10), _hit(3, 20))
        else:
            hits = (_hit(4, 30), _hit(5, 40))

        return RetrievalResult(
            query=query,
            mode=mode,
            top_k=top_k,
            filters=filters,
            hits=hits,
            embed_ms=2.0,
            search_ms=3.0,
            latency_ms=5.0,
        )


def test_run_evaluation_deduplicates_articles_and_calculates_metrics() -> None:
    retriever = FakeRetriever()
    queries = [
        EvalQuery(
            query_id="q1",
            text="general question",
            relevant_article_ids=frozenset({40}),
        )
    ]

    report = run_evaluation(
        queries,
        retriever,
        modes=("semantic",),
        ks=(1, 2),
        repeats=2,
    )

    metrics = report.modes["semantic"]
    row = report.per_query[0]

    assert metrics.n_queries == 1
    assert row["retrieved_article_ids"] == [30, 40]
    assert row["reciprocal_rank"] == 0.5
    assert metrics.recall_at_k[2] == 1.0
    assert metrics.precision_at_k[2] == 0.5
    assert metrics.latency_ms_p50 == 5.0
    assert metrics.latency_ms_p95 == 5.0
    assert len(retriever.calls) == 3  # one warm-up plus two measured runs


def test_hybrid_and_semantic_use_same_filtered_query_subset() -> None:
    retriever = FakeRetriever()
    queries = [
        EvalQuery(
            query_id="plain",
            text="general question",
            relevant_article_ids=frozenset({40}),
        ),
        EvalQuery(
            query_id="filtered",
            text="filtered question",
            relevant_article_ids=frozenset({20}),
            filters=SearchFilters(topics=("science",)),
        ),
    ]

    report = run_evaluation(
        queries,
        retriever,
        modes=("semantic", "hybrid"),
        ks=(1, 3),
        repeats=1,
    )

    assert report.modes["semantic"].n_queries == 1
    assert report.modes["hybrid"].n_queries == 1
    assert [row["query_id"] for row in report.per_query] == [
        "filtered",
        "filtered",
    ]

    hybrid_calls = [call for call in retriever.calls if call[2] == "hybrid"]
    assert len(hybrid_calls) == 2  # warm-up plus measured run
    assert hybrid_calls[0][3] == SearchFilters(topics=("science",))


def test_hybrid_is_omitted_when_no_queries_have_active_filters() -> None:
    retriever = FakeRetriever()
    queries = [
        EvalQuery(
            query_id="q1",
            text="general question",
            relevant_article_ids=frozenset({40}),
        )
    ]

    report = run_evaluation(queries, retriever, repeats=1)

    assert "semantic" in report.modes
    assert "hybrid" not in report.modes
    assert all(call[2] == "semantic" for call in retriever.calls)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"queries": []},
        {"ks": ()},
        {"ks": (0,)},
        {"chunk_pool": 0},
        {"repeats": 0},
        {"modes": ("invalid",)},
    ],
)
def test_run_evaluation_rejects_invalid_arguments(kwargs: dict) -> None:
    query = EvalQuery(
        query_id="q1",
        text="question",
        relevant_article_ids=frozenset({1}),
    )
    arguments = {
        "queries": [query],
        "retriever": FakeRetriever(),
    }
    arguments.update(kwargs)

    with pytest.raises(ValidationError):
        run_evaluation(**arguments)
