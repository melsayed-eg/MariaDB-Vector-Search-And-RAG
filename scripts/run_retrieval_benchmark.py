"""Run reproducible WikiRAG retrieval benchmarks against MariaDB."""

from __future__ import annotations

import argparse
from pathlib import Path

from wikirag.config import load_settings
from wikirag.db.repository import WikiRepository
from wikirag.embeddings import get_embedder
from wikirag.evaluation.dataset import load_queries
from wikirag.evaluation.metadata import collect_metadata, write_metadata
from wikirag.evaluation.run_eval import run_evaluation, write_report
from wikirag.retrieval.retriever import Retriever

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/eval/queries.jsonl"
SNAPSHOT = ROOT / "data/snapshot/wikipedia_snapshot.jsonl"
REPORTS = ROOT / "reports"
KS = (1, 3, 5, 10)
CHUNK_POOL = 30
REPEATS = 5


def main() -> None:
    """Execute both benchmarks and regenerate their reports.

    Raises:
        RuntimeError: If the configured database or corpus is unexpected.
        ValidationError: If evaluation inputs or filter compliance are invalid.
        DatabaseError: If MariaDB operations fail.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeats",
        type=int,
        default=REPEATS,
        help="Measured retrieval repetitions per query (default: 5)",
    )
    args = parser.parse_args()

    settings = load_settings()
    if settings.db.database != "wikirag":
        raise RuntimeError(
            "Benchmark requires the main 'wikirag' database; "
            f"configured database is {settings.db.database!r}"
        )

    queries = load_queries(DATASET, snapshot_path=SNAPSHOT)
    print(f"Loaded {len(queries)} evaluation questions.", flush=True)

    print("Loading embedding model...", flush=True)
    embedder = get_embedder()

    with WikiRepository(settings.db) as repo:
        articles = repo.count_articles()
        chunks = repo.count_chunks()

        if articles != 200 or chunks != 8743:
            raise RuntimeError(
                "Unexpected corpus size: "
                f"{articles} articles and {chunks} chunks; "
                "expected 200 articles and 8743 chunks"
            )

        retriever = Retriever(repo, embedder)

        for name, modes in (
            ("evaluation_semantic", ("semantic",)),
            ("evaluation_comparison", ("semantic", "hybrid")),
        ):
            print(f"\nRunning {name}...", flush=True)

            report = run_evaluation(
                queries,
                retriever,
                modes=modes,
                ks=KS,
                chunk_pool=CHUNK_POOL,
                repeats=args.repeats,
                require_compliance=True,
            )

            write_report(
                report,
                REPORTS / f"{name}.json",
                REPORTS / f"{name}.md",
            )

            for mode, metrics in report.modes.items():
                print(
                    f"{mode}: {metrics.n_queries} queries, "
                    f"MRR={metrics.mrr:.4f}, "
                    f"Recall@10={metrics.recall_at_k[10]:.4f}, "
                    f"P50={metrics.latency_ms_p50:.2f}ms, "
                    f"P95={metrics.latency_ms_p95:.2f}ms",
                    flush=True,
                )

        metadata = collect_metadata(
            connection=repo._conn,
            snapshot_path=SNAPSHOT,
            dataset_path=DATASET,
            embedding_model=settings.embedding_model,
            embedding_dimension=384,
            article_count=articles,
            chunk_count=chunks,
            ks=KS,
            chunk_pool=CHUNK_POOL,
            repeats=args.repeats,
        )
        write_metadata(metadata, REPORTS / "evaluation_metadata.json")

    print("\nBenchmark reports and metadata regenerated successfully.", flush=True)


if __name__ == "__main__":
    main()
