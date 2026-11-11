"""Test latency statistics recorded by retrieval evaluation."""

from __future__ import annotations

from statistics import stdev

import pytest

from wikirag.evaluation.run_eval import run_evaluation
from wikirag.models import EvalQuery, RetrievalResult


class FixedLatencyRetriever:
    """Return deterministic retrieval latencies."""

    def __init__(self, latencies: list[float]) -> None:
        self.latencies = iter(latencies)

    def retrieve(self, query, *, top_k=5, mode="semantic", filters=None):
        return RetrievalResult(
            query=query,
            mode=mode,
            top_k=top_k,
            filters=filters,
            hits=(),
            embed_ms=0.0,
            search_ms=0.0,
            latency_ms=next(self.latencies),
        )


def test_latency_samples_and_aggregate_statistics():
    """Preserve measured samples and calculate their statistics."""
    query = EvalQuery(
        query_id="latency_01",
        text="Test latency measurements",
        relevant_article_ids=(10,),
    )

    # The first retrieval is a warm-up and must not enter statistics.
    retriever = FixedLatencyRetriever([999.0, 10.0, 20.0, 30.0])

    report = run_evaluation(
        [query],
        retriever,
        modes=("semantic",),
        ks=(1,),
        chunk_pool=1,
        repeats=3,
    )

    row = report.per_query[0]
    assert row["latency_samples_ms"] == [10.0, 20.0, 30.0]
    assert row["latency_ms"] == pytest.approx(20.0)
    assert row["latency_stddev_ms"] == pytest.approx(stdev([10.0, 20.0, 30.0]))

    aggregate = row["aggregate_latency"]
    assert aggregate["latency_mean_ms"] == pytest.approx(20.0)
    assert aggregate["latency_stddev_ms"] == pytest.approx(stdev([10.0, 20.0, 30.0]))
    assert aggregate["latency_sample_count"] == 3
    assert aggregate["latency_raw_p50_ms"] == pytest.approx(20.0)
    assert aggregate["latency_raw_p95_ms"] == pytest.approx(29.0)


def test_single_repeat_has_zero_standard_deviation():
    """One measured sample must not cause a statistics exception."""
    query = EvalQuery(
        query_id="latency_02",
        text="Single sample",
        relevant_article_ids=(10,),
    )
    retriever = FixedLatencyRetriever([999.0, 12.0])

    report = run_evaluation(
        [query],
        retriever,
        modes=("semantic",),
        ks=(1,),
        chunk_pool=1,
        repeats=1,
    )

    row = report.per_query[0]
    assert row["latency_samples_ms"] == [12.0]
    assert row["latency_stddev_ms"] == 0.0
    assert row["aggregate_latency"]["latency_stddev_ms"] == 0.0
