"""Provide command-line access to the WikiRAG application."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from wikirag.config import load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.embeddings import get_embedder
from wikirag.errors import WikiRagError
from wikirag.ingestion.pipeline import ingest_snapshot
from wikirag.ingestion.wikipedia import build_snapshot


def build_parser() -> argparse.ArgumentParser:
    """Build the WikiRAG command-line parser.

    Returns:
        argparse.ArgumentParser: Parser with supported subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="wikirag",
        description="Wikipedia vector search and RAG using MariaDB.",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    commands.add_parser(
        "init-db",
        help="Create or verify the MariaDB schema.",
    )

    snapshot_parser = commands.add_parser(
        "build-snapshot",
        help="Download Wikipedia articles into a reproducible snapshot.",
    )
    snapshot_parser.add_argument(
        "--seed",
        type=Path,
        default=Path("data/seed_titles.csv"),
        help="Path to the Wikipedia seed titles CSV.",
    )
    snapshot_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSONL snapshot path.",
    )

    ingest_parser = commands.add_parser(
        "ingest",
        help="Ingest Wikipedia articles and embeddings into MariaDB.",
    )
    ingest_parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("data/snapshot/wikipedia_snapshot.jsonl"),
        help="Path to the Wikipedia JSONL snapshot.",
    )
    ingest_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of articles to process.",
    )

    return parser


def run_init_db() -> None:
    """Initialize or verify the application database schema.

    Returns:
        None: The schema has been initialized or verified.

    Raises:
        WikiRagError: If configuration or database setup fails.
    """
    config = load_settings().db

    with closing(get_connection(config)) as conn:
        init_schema(conn)

    print("MariaDB schema initialized and verified.")


def run_build_snapshot(seed_path: Path, output_path: Path) -> None:
    """Build a reproducible Wikipedia snapshot from seed titles.

    Args:
        seed_path: CSV file containing Wikipedia seed titles.
        output_path: Destination for the JSONL snapshot.

    Returns:
        None: The snapshot has been generated successfully.

    Raises:
        WikiRagError: If snapshot validation or fetching fails.
    """
    article_count = build_snapshot(
        seed_path,
        output_path,
    )

    print(f"Snapshot created successfully: {article_count} articles.")
    print(f"Snapshot saved to: {output_path}")


def run_ingest(snapshot_path: Path, limit: int | None = None) -> int:
    """Ingest Wikipedia snapshot articles into MariaDB.

    Args:
        snapshot_path: Path to the Wikipedia JSONL snapshot.
        limit: Optional maximum number of articles to process.

    Returns:
        int: Zero if all processed articles succeed, otherwise one.

    Raises:
        WikiRagError: If embedding, configuration, or database
            operations fail.
    """
    settings = load_settings()
    embedder = get_embedder()

    with WikiRepository(settings.db) as repo:
        report = ingest_snapshot(
            snapshot_path,
            repo,
            embedder,
            limit=limit,
        )

    print("Wikipedia ingestion completed.")
    print(f"Inserted: {report.inserted}")
    print(f"Updated: {report.updated}")
    print(f"Skipped: {report.skipped}")
    print(f"Failed: {len(report.failed)}")

    if report.failed:
        print("Failed articles:", file=sys.stderr)

        for title, message in report.failed:
            print(f"  {title}: {message}", file=sys.stderr)

        return 1

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the requested WikiRAG command.

    Args:
        argv: Optional command-line arguments. Uses sys.argv
            when omitted.

    Returns:
        int: Zero for success and one for an application error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init-db":
            run_init_db()

        elif args.command == "build-snapshot":
            run_build_snapshot(
                args.seed,
                args.output,
            )

        elif args.command == "ingest":
            return run_ingest(
                args.snapshot,
                args.limit,
            )

    except WikiRagError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
