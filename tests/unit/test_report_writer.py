"""Unit tests for evaluation report output."""

import json

import pytest

from wikirag.errors import ValidationError
from wikirag.evaluation.run_eval import write_report
from wikirag.models import EvalReport, ModeMetrics


def _report() -> EvalReport:
    return EvalReport(
        embedding_model="test-model",
        corpus_articles=10,
        corpus_chunks=25,
        ks=(1, 3),
        modes={
            "semantic": ModeMetrics(
                n_queries=2,
                recall_at_k={1: 0.5, 3: 1.0},
                precision_at_k={1: 0.5, 3: 0.3333},
                mrr=0.75,
                latency_ms_p50=12.5,
                latency_ms_p95=18.0,
            )
        },
        per_query=(
            {
                "query_id": "q1",
                "query": "test query",
                "mode": "semantic",
                "retrieved_article_ids": [10, 20],
                "reciprocal_rank": 1.0,
                "latency_ms": 12.5,
            },
        ),
    )


def test_write_report_creates_valid_json_and_markdown(tmp_path) -> None:
    json_path = tmp_path / "reports" / "report.json"
    md_path = tmp_path / "reports" / "report.md"

    write_report(_report(), json_path, md_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert data["embedding_model"] == "test-model"
    assert data["corpus_articles"] == 10
    assert data["modes"]["semantic"]["mrr"] == 0.75

    assert "# WikiRAG Retrieval Evaluation" in markdown
    assert "| Mode | Queries | MRR | Recall@1 | Recall@3 | Precision@1 | Precision@3 | P50 latency (ms) | P95 latency (ms) |" in markdown
    assert "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |" in markdown
    assert "| semantic | 2 | 0.7500 | 0.5000 | 1.0000 | 0.5000 | 0.3333 | 12.50 | 18.00 |" in markdown
    assert "| q1 | semantic | 1.0000 | 12.50 | 10, 20 |" in markdown


def test_write_report_handles_empty_results(tmp_path) -> None:
    report = EvalReport(
        embedding_model="test-model",
        corpus_articles=0,
        corpus_chunks=0,
        ks=(1,),
        modes={},
        per_query=(),
    )

    json_path = tmp_path / "empty.json"
    md_path = tmp_path / "empty.md"

    write_report(report, json_path, md_path)

    markdown = md_path.read_text(encoding="utf-8")
    assert "No aggregate results are available." in markdown
    assert "No per-query results are available." in markdown
    assert json.loads(json_path.read_text(encoding="utf-8"))["modes"] == {}


def test_write_report_rejects_same_output_path(tmp_path) -> None:
    path = tmp_path / "report.out"

    with pytest.raises(ValidationError, match="must be different"):
        write_report(_report(), path, path)


def test_write_report_rejects_wrong_report_type(tmp_path) -> None:
    with pytest.raises(ValidationError, match="EvalReport"):
        write_report(
            object(),
            tmp_path / "report.json",
            tmp_path / "report.md",
        )


def test_write_report_rejects_non_path_arguments() -> None:
    with pytest.raises(ValidationError, match="pathlib.Path"):
        write_report(_report(), "report.json", "report.md")
