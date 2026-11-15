"""Experiment: compare retrieval quality for different chunk sizes and overlaps."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wikirag.config import DbConfig, load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.embeddings import Embedder, SentenceTransformerEmbedder
from wikirag.errors import ValidationError, WikiRagError
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


def _git_output(*args: str) -> str:
    """Run a git command and return its output, or "unknown" if it fails.

    Args:
        *args: Arguments passed to git.

    Returns:
        The stripped standard output, or "unknown".
    """
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def current_git_commit() -> str:
    """Return the current git commit hash, or "unknown" if it cannot be read.

    Returns:
        The commit hash.
    """
    return _git_output("rev-parse", "HEAD")


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


def collect_run_metadata(config: DbConfig) -> dict[str, Any]:
    """Collect the conditions of this run so it can be reproduced.

    Args:
        config: Connection settings of the experiment database.

    Returns:
        Date, Python, operating system, hardware, MariaDB version, HNSW settings
        and git working-tree status. Values that cannot be read are "unknown".
    """
    mariadb_version = "unknown"
    hnsw: dict[str, str] = {}
    try:
        with closing(get_connection(config)) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version")
            row = cursor.fetchone()
            if row:
                mariadb_version = str(row["version"])
            cursor.execute("SHOW VARIABLES LIKE 'mhnsw%'")
            hnsw = {str(r["Variable_name"]): str(r["Value"]) for r in cursor.fetchall()}
    except Exception:  # metadata must never stop the experiment
        pass
    return {
        "run_utc": datetime.now(UTC).isoformat(),
        "python_version": sys.version.split()[0],
        "operating_system": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "machine": platform.machine(),
        "mariadb_version": mariadb_version,
        "hnsw_session_variables": hnsw,
        "git_worktree_status": _git_output("status", "--porcelain"),
    }


def _mode_summary(metrics: Any) -> dict[str, object]:
    """Convert one mode's metrics into a JSON-friendly dictionary.

    Args:
        metrics: A ModeMetrics-like object.

    Returns:
        The metrics as a dictionary.
    """
    return {
        "n_queries": metrics.n_queries,
        "recall_at_k": metrics.recall_at_k,
        "precision_at_k": metrics.precision_at_k,
        "mrr": metrics.mrr,
        "latency_ms_p50": metrics.latency_ms_p50,
        "latency_ms_p95": metrics.latency_ms_p95,
    }


def run_setting(
    *,
    config: DbConfig,
    embedder: Embedder,
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

    Raises:
        WikiRagError: If any article failed to ingest or no chunks were stored,
            so no measurements are published from an incomplete corpus.
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
        if ingest.failed:
            title, reason = ingest.failed[0]
            raise WikiRagError(
                f"Ingestion failed for {len(ingest.failed)} article(s) at "
                f"{max_chars}/{overlap_chars}; first: {title!r}: {reason}"
            )
        chunk_count = repo.count_chunks()
        if chunk_count == 0:
            raise WikiRagError(f"No chunks were stored at {max_chars}/{overlap_chars}")

        retriever = Retriever(repo, embedder)
        # semantic alone uses every query; with hybrid, both use the filtered subset
        full_report = run_evaluation(
            queries, retriever, modes=("semantic",), ks=DEFAULT_KS, repeats=repeats
        )
        report = run_evaluation(
            queries,
            retriever,
            modes=("semantic", "hybrid"),
            ks=DEFAULT_KS,
            repeats=repeats,
            require_compliance=True,
        )

    label = f"{max_chars}_{overlap_chars}"
    write_report(report, out_dir / f"{label}.json", out_dir / f"{label}.md")
    write_report(full_report, out_dir / f"{label}_all.json", out_dir / f"{label}_all.md")
    modes = {name: _mode_summary(metrics) for name, metrics in report.modes.items()}
    modes["semantic_all_queries"] = _mode_summary(full_report.modes["semantic"])
    return {
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
        "articles_inserted": ingest.inserted,
        "articles_failed": len(ingest.failed),
        "chunks": chunk_count,
        "ingest_seconds": round(ingest_seconds, 1),
        "modes": modes,
    }


def run_chunk_size_comparison(
    settings: Sequence[tuple[int, int]],
    *,
    snapshot_path: Path,
    queries_path: Path,
    out_dir: Path,
    limit: int | None = None,
    repeats: int = 5,
    embedder: Embedder | None = None,
    config: DbConfig | None = None,
) -> dict[str, object]:
    """Run every chunk setting and write ``summary.json``.

    Args:
        settings: ``(max_chars, overlap_chars)`` pairs to compare.
        snapshot_path: Wikipedia snapshot file.
        queries_path: Evaluation query file.
        out_dir: Directory for the reports and the summary.
        limit: Ingest only this many articles; None means all.
        repeats: Latency repetitions per query.
        embedder: Embedder to use; the real model is loaded if omitted.
        config: Test database settings; taken from the configuration if omitted.

    Returns:
        The summary that was written to ``summary.json``.

    Raises:
        ValidationError: If the settings are empty or the database is unsafe.
        WikiRagError: If ingestion fails for any setting.
    """
    if not settings:
        raise ValidationError("At least one chunk setting is required")
    db_config = config if config is not None else experiment_database_config()
    chosen = embedder if embedder is not None else SentenceTransformerEmbedder()

    rows = [
        run_setting(
            config=db_config,
            embedder=chosen,
            snapshot_path=snapshot_path,
            queries_path=queries_path,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
            out_dir=out_dir,
            limit=limit,
            repeats=repeats,
        )
        for max_chars, overlap_chars in settings
    ]
    summary: dict[str, object] = {
        "snapshot_sha256": file_sha256(snapshot_path),
        "queries_sha256": file_sha256(queries_path),
        "embedding_model": chosen.model_name,
        "git_commit": current_git_commit(),
        "article_limit": limit,
        "repeats": repeats,
        "environment": collect_run_metadata(db_config),
        "results": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


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

    run_chunk_size_comparison(
        parse_settings(args.settings),
        snapshot_path=args.snapshot,
        queries_path=args.queries,
        out_dir=args.out_dir,
        limit=args.limit,
        repeats=args.repeats,
    )
    print(f"Wrote {args.out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
