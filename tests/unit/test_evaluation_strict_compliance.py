"""Test strict hybrid compliance enforcement in the evaluation runner."""

from unittest.mock import Mock

import pytest

from wikirag.errors import ValidationError
from wikirag.evaluation.run_eval import run_evaluation
from wikirag.models import EvalQuery, RetrievalResult, SearchFilters, SearchHit


def make_query():
    """Build a constrained evaluation query."""
    return EvalQuery(
        query_id="hyb_test",
        text="Find database articles",
        relevant_article_ids=(10,),
        filters=SearchFilters(topics=("databases",)),
    )


def make_result():
    """Build a deterministic retrieval result."""
    hit = SearchHit(
        chunk_id=100,
        article_id=10,
        article_title="Example",
        article_url="https://en.wikipedia.org/wiki/Example",
        chunk_index=0,
        section_title=None,
        text="Example",
        distance=0.2,
        score=0.8,
    )
    return RetrievalResult(
        query="Find database articles",
        mode="hybrid",
        top_k=10,
        filters=SearchFilters(topics=("databases",)),
        hits=(hit,),
        embed_ms=1.0,
        search_ms=2.0,
        latency_ms=3.0,
    )


def test_strict_mode_requires_metadata_repository():
    """Reject hybrid evaluation without independent metadata access."""
    retriever = Mock(spec=["retrieve"])
    retriever.retrieve.return_value = make_result()

    with pytest.raises(ValidationError, match="requires repository"):
        run_evaluation(
            [make_query()],
            retriever,
            modes=("hybrid",),
            ks=(1,),
            repeats=1,
            require_compliance=True,
        )


def test_strict_mode_rejects_filter_violations():
    """Reject results that violate the active SQL constraints."""
    retriever = Mock()
    retriever.retrieve.return_value = make_result()
    retriever._repo.get_article.return_value = None

    with pytest.raises(ValidationError, match="Hybrid filter violations"):
        run_evaluation(
            [make_query()],
            retriever,
            modes=("hybrid",),
            ks=(1,),
            repeats=1,
            require_compliance=True,
        )


def test_strict_mode_accepts_compliant_results():
    """Accept results whose stored metadata satisfies the constraints."""
    retriever = Mock()
    retriever.retrieve.return_value = make_result()

    article = Mock()
    article.article_id = 10
    article.topic = "databases"
    article.categories = ()
    article.length_chars = 1000

    retriever._repo.get_article.return_value = article

    report = run_evaluation(
        [make_query()],
        retriever,
        modes=("hybrid",),
        ks=(1,),
        repeats=1,
        require_compliance=True,
    )

    compliance = report.per_query[0]["filter_compliance"]
    assert compliance["returned_hits"] == 1
    assert compliance["violating_hits"] == 0
    assert compliance["compliance_rate"] == 1.0
