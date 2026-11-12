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


def test_semantic_baseline_reports_violations_without_enforcing_filters():
    """Semantic retrieval remains unfiltered but measures constraint satisfaction."""
    retriever = Mock()
    retriever.retrieve.return_value = make_result()
    article = Mock()
    article.article_id = 10
    article.topic = "algorithms"
    article.categories = ()
    article.length_chars = 1000
    retriever._repo.get_article.return_value = article

    report = run_evaluation(
        [make_query()],
        retriever,
        modes=("semantic",),
        ks=(1,),
        repeats=1,
        require_compliance=True,
    )

    compliance = report.per_query[0]["filter_compliance"]
    assert compliance["returned_hits"] == 1
    assert compliance["violating_hits"] == 1
    assert compliance["compliance_rate"] == 0.0
    assert compliance["violations"][0]["failed_constraints"] == ["topics"]
    assert all(call.kwargs["filters"] is None for call in retriever.retrieve.call_args_list)


def test_markdown_compares_semantic_and_hybrid_constraint_satisfaction(tmp_path):
    """Report semantic violations alongside enforced hybrid compliance."""
    from wikirag.evaluation.run_eval import write_report

    retriever = Mock()
    retriever._embedder.model_name = "test-embedding-model"
    retriever._repo.count_articles.return_value = 1
    retriever._repo.count_chunks.return_value = 1
    retriever.retrieve.return_value = make_result()

    article = Mock()
    article.article_id = 10
    article.topic = "algorithms"
    article.categories = ()
    article.length_chars = 1000

    def get_article(article_id):
        if retriever.retrieve.call_args.kwargs["filters"] is None:
            return article
        compliant_article = Mock()
        compliant_article.article_id = article_id
        compliant_article.topic = "databases"
        compliant_article.categories = ()
        compliant_article.length_chars = 1000
        return compliant_article

    retriever._repo.get_article.side_effect = get_article

    report = run_evaluation(
        [make_query()],
        retriever,
        modes=("semantic", "hybrid"),
        ks=(1,),
        repeats=1,
        require_compliance=True,
    )

    assert [row["filter_compliance"]["violating_hits"] for row in report.per_query] == [1, 0]

    json_path = tmp_path / "evaluation.json"
    md_path = tmp_path / "evaluation.md"
    write_report(report, json_path, md_path)

    markdown = md_path.read_text()
    assert "## Constraint satisfaction comparison" in markdown
    assert "| semantic | 1 | 1 | 0 | 1 | 0 | 0.0000 |" in markdown
    assert "| hybrid | 1 | 1 | 1 | 0 | 0 | 1.0000 |" in markdown
