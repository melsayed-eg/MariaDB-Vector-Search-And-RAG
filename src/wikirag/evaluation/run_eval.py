"""Run article-level retrieval evaluation and aggregate performance metrics."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from statistics import mean
from typing import Protocol

from wikirag.config import EMBEDDING_MODEL_NAME
from wikirag.errors import ValidationError
from wikirag.evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from wikirag.models import (
    EvalQuery,
    EvalReport,
    ModeMetrics,
    RAGAnswer,
    RetrievalMode,
    RetrievalResult,
    SearchFilters,
)
from wikirag.rag.generator import Generator


class EvaluationRetriever(Protocol):
    """Minimal retriever interface required by evaluation."""

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        mode: RetrievalMode = "semantic",
        filters: SearchFilters | None = None,
    ) -> RetrievalResult: ...


def _article_ids(result: RetrievalResult) -> list[int]:
    """Return unique article IDs in ranked chunk-hit order."""
    return list(dict.fromkeys(hit.article_id for hit in result.hits))


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Calculate a linearly interpolated percentile."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def run_evaluation(
    queries: Sequence[EvalQuery],
    retriever: EvaluationRetriever,
    *,
    modes: Sequence[RetrievalMode] = ("semantic", "hybrid"),
    ks: Sequence[int] = (1, 3, 5, 10),
    chunk_pool: int = 30,
    repeats: int = 5,
) -> EvalReport:
    """Evaluate retrieval quality and latency for the requested modes."""
    if not queries:
        raise ValidationError("queries must not be empty")
    if not modes or any(mode not in ("semantic", "hybrid") for mode in modes):
        raise ValidationError("modes must contain semantic and/or hybrid")
    if not ks or any(not isinstance(k, int) or isinstance(k, bool) or k < 1 for k in ks):
        raise ValidationError("ks must contain positive integers")
    if len(set(ks)) != len(ks):
        raise ValidationError("ks must not contain duplicates")
    if not isinstance(chunk_pool, int) or isinstance(chunk_pool, bool):
        raise ValidationError("chunk_pool must be an integer")
    if not 1 <= chunk_pool <= 100:
        raise ValidationError("chunk_pool must be between 1 and 100")
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise ValidationError("repeats must be a positive integer")

    query_ids = [query.query_id for query in queries]
    if len(set(query_ids)) != len(query_ids):
        raise ValidationError("query_id values must be unique")
    if any(not query.relevant_article_ids for query in queries):
        raise ValidationError("every query must have relevant article IDs")

    requested_modes = tuple(dict.fromkeys(modes))
    filtered_queries = [
        query
        for query in queries
        if query.filters is not None and not query.filters.is_empty()
    ]

    evaluations: dict[str, list[dict]] = {mode: [] for mode in requested_modes}

    # Compare semantic and hybrid on the same filtered-query subset.
    compare_modes = (
        "semantic" in requested_modes
        and "hybrid" in requested_modes
        and bool(filtered_queries)
    )

    for mode in requested_modes:
        if mode == "hybrid" or (mode == "semantic" and compare_modes):
            eligible_queries = filtered_queries
        else:
            eligible_queries = list(queries)

        if mode == "hybrid" and not eligible_queries:
            continue

        for query in eligible_queries:
            filters = query.filters if mode == "hybrid" else None

            # Warm up before collecting latency samples.
            retriever.retrieve(
                query.text,
                top_k=chunk_pool,
                mode=mode,
                filters=filters,
            )

            samples: list[RetrievalResult] = []
            for _ in range(repeats):
                samples.append(
                    retriever.retrieve(
                        query.text,
                        top_k=chunk_pool,
                        mode=mode,
                        filters=filters,
                    )
                )

            # Quality metrics use the last measured result. Latency is averaged
            # over repeats for this query before cross-query percentiles.
            result = samples[-1]
            ranked_articles = _article_ids(result)
            relevant = query.relevant_article_ids
            reciprocal = reciprocal_rank(ranked_articles, relevant)

            evaluations[mode].append(
                {
                    "query_id": query.query_id,
                    "query": query.text,
                    "mode": mode,
                    "relevant_article_ids": sorted(relevant),
                    "retrieved_article_ids": ranked_articles,
                    "reciprocal_rank": reciprocal,
                    "latency_ms": mean(sample.latency_ms for sample in samples),
                    "recall_at_k": {k: recall_at_k(ranked_articles, relevant, k) for k in ks},
                    "precision_at_k": {k: precision_at_k(ranked_articles, relevant, k) for k in ks},
                }
            )

    mode_metrics: dict[str, ModeMetrics] = {}
    per_query: list[dict] = []

    for mode in requested_modes:
        rows = evaluations[mode]
        if not rows:
            continue

        latencies = [row["latency_ms"] for row in rows]
        mode_metrics[mode] = ModeMetrics(
            n_queries=len(rows),
            recall_at_k={k: mean(row["recall_at_k"][k] for row in rows) for k in ks},
            precision_at_k={k: mean(row["precision_at_k"][k] for row in rows) for k in ks},
            mrr=mean(row["reciprocal_rank"] for row in rows),
            latency_ms_p50=_percentile(latencies, 0.50),
            latency_ms_p95=_percentile(latencies, 0.95),
        )
        per_query.extend(rows)

    repo = getattr(retriever, "_repo", None)
    count_articles = getattr(repo, "count_articles", None)
    count_chunks = getattr(repo, "count_chunks", None)

    return EvalReport(
        embedding_model=getattr(
            getattr(retriever, "_embedder", None),
            "model_name",
            EMBEDDING_MODEL_NAME,
        ),
        corpus_articles=count_articles() if callable(count_articles) else 0,
        corpus_chunks=count_chunks() if callable(count_chunks) else 0,
        ks=tuple(ks),
        modes=mode_metrics,
        per_query=tuple(per_query),
    )


def run_rag_smoke_check(
    questions: Sequence[str],
    retriever: EvaluationRetriever,
    generator: Generator,
    *,
    top_k: int = 5,
) -> list[RAGAnswer]:
    """Run questions through the RAG pipeline as a basic smoke check."""
    from wikirag.rag.pipeline import answer_question

    if not questions:
        raise ValidationError("questions must not be empty")
    if any(not isinstance(question, str) or not question.strip() for question in questions):
        raise ValidationError("questions must contain non-empty strings")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 100:
        raise ValidationError("top_k must be an integer between 1 and 100")

    return [
        answer_question(question, retriever, generator, top_k=top_k)
        for question in questions
    ]


def write_report(
    report: EvalReport,
    json_path: Path,
    md_path: Path,
) -> None:
    """Write evaluation results as JSON and Markdown reports."""
    import json
    from dataclasses import asdict

    if not isinstance(report, EvalReport):
        raise ValidationError("report must be an EvalReport")
    if not isinstance(json_path, Path) or not isinstance(md_path, Path):
        raise ValidationError("report paths must be pathlib.Path instances")
    if json_path.resolve() == md_path.resolve():
        raise ValidationError("JSON and Markdown paths must be different")

    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(report)
    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# WikiRAG Retrieval Evaluation",
        "",
        f"- **Embedding model:** {report.embedding_model}",
        f"- **Corpus articles:** {report.corpus_articles}",
        f"- **Corpus chunks:** {report.corpus_chunks}",
        f"- **Evaluated K values:** {', '.join(map(str, report.ks))}",
        "",
        "## Aggregate results",
        "",
    ]

    if report.modes:
        headers = [
            "Mode",
            "Queries",
            "MRR",
            *(f"Recall@{k}" for k in report.ks),
            *(f"Precision@{k}" for k in report.ks),
            "P50 latency (ms)",
            "P95 latency (ms)",
        ]
        separators = [
            "---",
            "---:",
            "---:",
            *("---:" for _ in report.ks),
            *("---:" for _ in report.ks),
            "---:",
            "---:",
        ]
        lines.extend([
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(separators) + " |",
        ])

        for mode, metrics in report.modes.items():
            values = [
                mode,
                str(metrics.n_queries),
                f"{metrics.mrr:.4f}",
                *(f"{metrics.recall_at_k.get(k, 0.0):.4f}" for k in report.ks),
                *(f"{metrics.precision_at_k.get(k, 0.0):.4f}" for k in report.ks),
                f"{metrics.latency_ms_p50:.2f}",
                f"{metrics.latency_ms_p95:.2f}",
            ]
            lines.append("| " + " | ".join(values) + " |")
    else:
        lines.append("No aggregate results are available.")

    lines.extend(["", "## Per-query results", ""])

    if report.per_query:
        lines.extend([
            "| Query ID | Mode | Reciprocal rank | Latency (ms) | Retrieved article IDs |",
            "|---|---|---:|---:|---|",
        ])
        for row in report.per_query:
            query_id = str(row.get("query_id", "")).replace("|", "\\|")
            mode = str(row.get("mode", "")).replace("|", "\\|")
            retrieved = ", ".join(
                str(article_id)
                for article_id in row.get("retrieved_article_ids", [])
            )
            lines.append(
                f"| {query_id} | {mode} | "
                f"{row.get('reciprocal_rank', 0.0):.4f} | "
                f"{row.get('latency_ms', 0.0):.2f} | {retrieved} |"
            )
    else:
        lines.append("No per-query results are available.")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
