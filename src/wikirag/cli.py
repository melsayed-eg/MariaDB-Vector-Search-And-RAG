"""Provide command-line access to the WikiRAG application."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import closing
from datetime import datetime
from pathlib import Path

from wikirag.config import load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.embeddings import get_embedder
from wikirag.errors import ValidationError, WikiRagError
from wikirag.ingestion.pipeline import ingest_snapshot
from wikirag.ingestion.wikipedia import build_snapshot
from wikirag.models import RetrievalMode, SearchFilters
from wikirag.retrieval.retriever import Retriever


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

    search_parser = commands.add_parser(
        "search",
        help="Search Wikipedia chunks using semantic or hybrid retrieval.",
    )
    search_parser.add_argument(
        "query",
        help="Natural-language search question.",
    )
    search_parser.add_argument(
        "--mode",
        choices=("semantic", "hybrid"),
        default="semantic",
        help="Retrieval mode (default: semantic).",
    )
    search_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum matching chunks, from 1 to 100.",
    )

    # Repeated topic/category flags use OR within each filter.
    search_parser.add_argument(
        "--topic",
        action="append",
        default=[],
        help="Required article topic; may be repeated.",
    )
    search_parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Required Wikipedia category; may be repeated.",
    )
    search_parser.add_argument(
        "--article-id",
        type=int,
        action="append",
        default=[],
        help="Include an article ID; may be repeated.",
    )
    search_parser.add_argument(
        "--exclude-article-id",
        type=int,
        action="append",
        default=[],
        help="Exclude an article ID; may be repeated.",
    )
    search_parser.add_argument(
        "--min-length-chars",
        type=int,
        default=None,
        help="Require article length strictly greater than this value.",
    )
    search_parser.add_argument(
        "--edited-since",
        type=str,
        default=None,
        help="Earliest revision date in naive UTC ISO format.",
    )
    search_parser.add_argument(
        "--linked-from-article-id",
        type=int,
        default=None,
        help="Only search articles linked from this article ID.",
    )
    search_parser.add_argument(
        "--max-distance",
        type=float,
        default=None,
        help="Maximum cosine distance, between 0 and 2.",
    )

    return parser


def build_search_filters(args: argparse.Namespace) -> SearchFilters | None:
    """Validate search options and build the shared filter object.

    Args:
        args: Parsed command-line search arguments.

    Returns:
        SearchFilters | None: Valid SQL filters in hybrid mode,
        otherwise None.

    Raises:
        ValidationError: If the query, limits, date, or filters
            are invalid or inconsistent with the retrieval mode.
    """
    if not args.query.strip():
        raise ValidationError("Search query must not be blank")

    if not 1 <= args.top_k <= 100:
        raise ValidationError("--top-k must be between 1 and 100")

    edited_since = None

    if args.edited_since is not None:
        try:
            edited_since = datetime.fromisoformat(args.edited_since)
        except ValueError as error:
            raise ValidationError("--edited-since must contain a valid ISO date") from error

    filters = SearchFilters(
        topics=tuple(args.topic),
        categories=tuple(args.category),
        article_ids=tuple(args.article_id),
        exclude_article_ids=tuple(args.exclude_article_id),
        min_length_chars=args.min_length_chars,
        edited_since=edited_since,
        linked_from_article_id=args.linked_from_article_id,
        max_distance=args.max_distance,
    )

    filters.validate()

    if args.mode == "hybrid":
        if filters.is_empty():
            raise ValidationError("Hybrid search requires at least one SQL filter")
        return filters

    # Avoid silently ignoring filters in semantic mode.
    if not filters.is_empty():
        raise ValidationError("SQL filters require --mode hybrid")

    return None


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


def run_search(
    query: str,
    *,
    top_k: int = 5,
    mode: RetrievalMode = "semantic",
    filters: SearchFilters | None = None,
) -> None:
    """Retrieve and display matching Wikipedia text chunks.

    Args:
        query: Natural-language question or search text.
        top_k: Maximum number of ranked chunks.
        mode: Semantic or hybrid retrieval mode.
        filters: Optional database-native SQL constraints.

    Returns:
        None: Prints ranked matches and retrieval timing.

    Raises:
        WikiRagError: If embedding, retrieval, or database access fails.
    """
    settings = load_settings()

    with WikiRepository(settings.db) as repo:
        retriever = Retriever(repo, get_embedder())

        result = retriever.retrieve(
            query,
            top_k=top_k,
            mode=mode,
            filters=filters,
        )

    print(f"Search mode: {result.mode}")
    print(f"Matching chunks: {len(result.hits)}")

    if not result.hits:
        print("No matching Wikipedia chunks found.")

    for rank, hit in enumerate(result.hits, start=1):
        print()
        print(f"[{rank}] {hit.article_title}")
        print(f"Article ID: {hit.article_id}")
        print(f"Chunk index: {hit.chunk_index}")
        print(f"Distance: {hit.distance:.4f}")
        print(f"Similarity score: {hit.score:.4f}")
        print(f"Source: {hit.article_url}")

        # Display a readable preview rather than an entire long chunk.
        preview = " ".join(hit.text.split())
        if len(preview) > 250:
            preview = preview[:247] + "..."

        print(f"Text: {preview}")

    print()
    print(f"Embedding time: {result.embed_ms:.2f} ms")
    print(f"Search time: {result.search_ms:.2f} ms")
    print(f"Total retrieval time: {result.latency_ms:.2f} ms")


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

        elif args.command == "search":
            filters = build_search_filters(args)

            run_search(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                filters=filters,
            )

    except WikiRagError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
