"""Experiment: compare retrieval quality for different chunk sizes and overlaps."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections.abc import Sequence
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from wikirag.config import DbConfig, load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.embeddings import SentenceTransformerEmbedder
from wikirag.errors import ValidationError
from wikirag.evaluation.dataset import load_queries
from wikirag.evaluation.metadata import file_sha256
from wikirag.evaluation.run_eval import run_evaluation, write_report
from wikirag.ingestion.pipeline import ingest_snapshot
from wikirag.retrieval.retriever import Retriever

# planned settings from the blueprint: (max_chars, overlap_chars)
DEFAULT_SETTINGS: tuple[tuple[int, int], ...] = ((500, 75), (1000, 150), (1500, 200))
DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 10)


def parse_settings(values: Sequence[str]) -> list[tuple[int, int]]:
    """Parse chunk settings written as ``MAX:OVERLAP``, for example ``1000:150``.

    Args:
        values: The strings to parse.

    Returns:
        ``(max_chars, overlap_chars)`` pairs in the given order.

    Raises:
        ValidationError: If a value is malformed, overlap is not below max,
            or the list is empty or has duplicates.
    """
    settings: list[tuple[int, int]] = []
    for value in values:
        try:
            max_text, overlap_text = value.split(":")
            max_chars, overlap_chars = int(max_text), int(overlap_text)
        except ValueError as error:
            raise ValidationError(f"Setting must look like 1000:150, got {value!r}") from error
        if max_chars < 1 or overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValidationError(f"Invalid chunk setting {value!r}")
        settings.append((max_chars, overlap_chars))
    if not settings or len(set(settings)) != len(settings):
        raise ValidationError("Provide at least one setting, without duplicates")
    return settings


def current_git_commit() -> str:
    """Return the current git commit hash, or "unknown" if it cannot be read.

    Returns:
        The commit hash.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def experiment_database_config() -> DbConfig:
    """Return connection settings for the dedicated test database.

    Returns:
        Settings for the database whose name ends in ``_test``.

    Raises:
        ValidationError: If the test database name is unsafe.
    """
    settings = load_settings()
    name = settings.db_name_test
    if not name.endswith("_test") or name == settings.db.database:
        raise ValidationError("The experiment needs a separate database ending in _test")
    return replace(settings.db, database=name)


def run_setting(
    *,
    config: DbConfig,
    embedder: SentenceTransformerEmbedder,
    snapshot_path: Path,
    queries_path: Path,
    max_chars: int,
    overlap_chars: int,
    out_dir: Path,
    limit: int | None,
    repeats: int,
) -> dict[str, object]:
    """Ingest the snapshot with one chunk setting and evaluate retrieval.

    The test database is rebuilt first, so settings never mix.

    Args:
        config: Test database connection settings.
        embedder: Embedder used for chunks and queries.
        snapshot_path: Wikipedia snapshot file.
        queries_path: Evaluation query file (JSON or JSONL).
        max_chars: Maximum characters per chunk.
        overlap_chars: Overlap between chunks.
        out_dir: Directory for the per-setting reports.
        limit: Ingest only this many articles; None means all.
        repeats: Latency repetitions per query.

    Returns:
        A summary dictionary for the comparison.
    """
    queries = load_queries(queries_path, snapshot_path=snapshot_path)
    with closing(get_connection(config)) as conn:
        init_schema(conn, recreate=True)

    with WikiRepository(config) as repo:
        started = time.perf_counter()
        ingest = ingest_snapshot(
            snapshot_path,
            repo,
            embedder,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            limit=limit,
        )
        ingest_seconds = time.perf_counter() - started
        chunk_count = repo.count_chunks()
        retriever = Retriever(repo, embedder)
        # semantic alone uses every query; with hybrid, both use the filtered subset
        full_report = run_evaluation(
            queries, retriever, modes=("semantic",), ks=DEFAULT_KS, repeats=repeats
        )
        report = run_evaluation(
            queries, retriever, modes=("semantic", "hybrid"), ks=DEFAULT_KS, repeats=repeats
        )

    label = f"{max_chars}_{overlap_chars}"
    write_report(report, out_dir / f"{label}.json", out_dir / f"{label}.md")
    write_report(full_report, out_dir / f"{label}_all.json", out_dir / f"{label}_all.md")
    modes = {
        name: {
            "n_queries": metrics.n_queries,
            "recall_at_k": metrics.recall_at_k,
            "precision_at_k": metrics.precision_at_k,
            "mrr": metrics.mrr,
            "latency_ms_p50": metrics.latency_ms_p50,
            "latency_ms_p95": metrics.latency_ms_p95,
        }
        for name, metrics in report.modes.items()
    }
    full = full_report.modes["semantic"]
    modes["semantic_all_queries"] = {
        "n_queries": full.n_queries,
        "recall_at_k": full.recall_at_k,
        "precision_at_k": full.precision_at_k,
        "mrr": full.mrr,
        "latency_ms_p50": full.latency_ms_p50,
        "latency_ms_p95": full.latency_ms_p95,
    }
    return {
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
        "articles_inserted": ingest.inserted,
        "articles_failed": len(ingest.failed),
        "chunks": chunk_count,
        "ingest_seconds": round(ingest_seconds, 1),
        "modes": modes,
    }


def main() -> None:
    """Run the chunk-size experiment from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=Path("data/eval/queries.jsonl"))
    parser.add_argument(
        "--snapshot", type=Path, default=Path("data/snapshot/wikipedia_snapshot.jsonl")
    )
    parser.add_argument("--out-dir", type=Path, default=Path("results/experiments/chunk_size"))
    parser.add_argument("--settings", nargs="+", default=[f"{m}:{o}" for m, o in DEFAULT_SETTINGS])
    parser.add_argument("--limit", type=int, default=None, help="articles to ingest (dry runs)")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    settings = parse_settings(args.settings)
    config = experiment_database_config()
    embedder = SentenceTransformerEmbedder()

    rows = [
        run_setting(
            config=config,
            embedder=embedder,
            snapshot_path=args.snapshot,
            queries_path=args.queries,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            out_dir=args.out_dir,
            limit=args.limit,
            repeats=args.repeats,
        )
        for max_chars, overlap_chars in settings
    ]

    summary = {
        "snapshot_sha256": file_sha256(args.snapshot),
        "queries_sha256": file_sha256(args.queries),
        "embedding_model": embedder.model_name,
        "git_commit": current_git_commit(),
        "article_limit": args.limit,
        "repeats": args.repeats,
        "results": rows,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
