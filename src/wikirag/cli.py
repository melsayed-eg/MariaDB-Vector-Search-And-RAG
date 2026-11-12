"""Provide command-line access to the WikiRAG application."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from wikirag.config import load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.embeddings import get_embedder
from wikirag.errors import ValidationError, WikiRagError
from wikirag.experiments.metric_mismatch import run_metric_mismatch
from wikirag.experiments.reporting import write_experiment_report
from wikirag.experiments.transaction_visibility import run_transaction_visibility
from wikirag.ingestion.pipeline import ingest_snapshot
from wikirag.ingestion.wikipedia import build_snapshot
from wikirag.models import RetrievalMode, SearchFilters
from wikirag.rag.generator import ExtractiveGenerator
from wikirag.rag.pipeline import answer_question
from wikirag.retrieval.retriever import Retriever


def add_retrieval_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared search and RAG retrieval options.

    Args:
        parser: Subcommand parser to configure.

    Returns:
        None: Arguments are registered on the parser.
    """
    parser.add_argument(
        "query",
        help="Natural-language question or search query.",
    )
    parser.add_argument(
        "--mode",
        choices=("semantic", "hybrid"),
        default="semantic",
        help="Retrieval mode (default: semantic).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum matching chunks, from 1 to 100.",
    )
    parser.add_argument(
        "--topic",
        action="append",
        default=[],
        help="Required article topic; may be repeated.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Required Wikipedia category; may be repeated.",
    )
    parser.add_argument(
        "--article-id",
        type=int,
        action="append",
        default=[],
        help="Include an article ID; may be repeated.",
    )
    parser.add_argument(
        "--exclude-article-id",
        type=int,
        action="append",
        default=[],
        help="Exclude an article ID; may be repeated.",
    )
    parser.add_argument(
        "--min-length-chars",
        type=int,
        default=None,
        help="Minimum article length in characters.",
    )
    parser.add_argument(
        "--edited-since",
        type=str,
        default=None,
        help="Earliest revision date in naive UTC ISO format.",
    )
    parser.add_argument(
        "--linked-from-article-id",
        type=int,
        default=None,
        help="Search articles linked from this article ID.",
    )
    parser.add_argument(
        "--max-distance",
        type=float,
        default=None,
        help="Maximum cosine distance, between 0 and 2.",
    )


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
    add_retrieval_arguments(search_parser)

    ask_parser = commands.add_parser(
        "ask",
        help="Answer questions using retrieved Wikipedia sources.",
    )
    add_retrieval_arguments(ask_parser)
    ask_parser.add_argument(
        "--max-context-chars",
        type=int,
        default=6000,
        help="Maximum RAG context length in characters.",
    )

    evaluate_parser = commands.add_parser(
        "evaluate",
        help="Run the reproducible Wikipedia retrieval benchmark.",
    )
    evaluate_parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Measured repetitions per query (default: 5).",
    )

    stats_parser = commands.add_parser(
        "stats",
        help="Display Wikipedia corpus statistics from MariaDB.",
    )
    stats_parser.add_argument(
        "--min-category-articles",
        type=int,
        default=1,
        help="Minimum articles required for a category.",
    )
    stats_parser.add_argument(
        "--show-categories",
        action="store_true",
        help="Display category names as well as their count.",
    )

    experiment_parser = commands.add_parser(
        "experiment",
        help="Run MariaDB native-vector depth experiments.",
    )
    experiment_commands = experiment_parser.add_subparsers(
        dest="experiment_name",
        required=True,
    )

    metric_parser = experiment_commands.add_parser(
        "metric-mismatch",
        help="Compare distance expressions and HNSW index usage.",
    )
    metric_parser.add_argument(
        "--query",
        default="How does quicksort work?",
        help="Question used to create the experiment query vector.",
    )
    metric_parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Measured executions per SQL variant (minimum: 5).",
    )
    metric_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON report path.",
    )

    visibility_parser = experiment_commands.add_parser(
        "transaction-visibility",
        help="Test vector transaction visibility in an isolated test database.",
    )
    visibility_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination JSON report path.",
    )

    return parser


def build_search_filters(args: argparse.Namespace) -> SearchFilters | None:
    """Validate retrieval options and build the shared filter object.

    Args:
        args: Parsed search or RAG command arguments.

    Returns:
        SearchFilters | None: SQL filters for hybrid mode,
            otherwise None.

    Raises:
        ValidationError: If retrieval arguments are invalid.
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

    # Prevent silently ignoring SQL filters during semantic search.
    if not filters.is_empty():
        raise ValidationError("SQL filters require --mode hybrid")

    return None


def validate_report_path(output_path: Path) -> None:
    """Validate a new JSON experiment report destination.

    Args:
        output_path: Path where the report would be written.

    Returns:
        None: The destination is valid and does not exist.

    Raises:
        ValidationError: If the path is invalid or already exists.
    """
    if not isinstance(output_path, Path) or output_path.suffix.lower() != ".json":
        raise ValidationError("--output must be a JSON file")

    if output_path.exists():
        raise ValidationError(
            f"Report already exists: {output_path}. "
            "Choose a new output path to preserve previous measurements."
        )


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
    """Build a Wikipedia snapshot from seed titles.

    Args:
        seed_path: CSV containing Wikipedia seed titles.
        output_path: Destination for the JSONL snapshot.

    Returns:
        None: The snapshot has been generated.

    Raises:
        WikiRagError: If snapshot validation or fetching fails.
    """
    article_count = build_snapshot(seed_path, output_path)

    print(f"Snapshot created successfully: {article_count} articles.")
    print(f"Snapshot saved to: {output_path}")


def run_ingest(snapshot_path: Path, limit: int | None = None) -> int:
    """Ingest Wikipedia snapshot articles into MariaDB.

    Args:
        snapshot_path: Path to the Wikipedia JSONL snapshot.
        limit: Optional maximum number of articles.

    Returns:
        int: Zero if every article succeeds, otherwise one.

    Raises:
        WikiRagError: If ingestion setup or database access fails.
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
    """Retrieve and display matching Wikipedia chunks.

    Args:
        query: Natural-language search text.
        top_k: Maximum number of ranked chunks.
        mode: Semantic or hybrid retrieval mode.
        filters: Optional MariaDB SQL constraints.

    Returns:
        None: Prints matching chunks and retrieval timings.

    Raises:
        WikiRagError: If retrieval or database access fails.
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

        preview = " ".join(hit.text.split())
        if len(preview) > 250:
            preview = preview[:247] + "..."

        print(f"Text: {preview}")

    print()
    print(f"Embedding time: {result.embed_ms:.2f} ms")
    print(f"Search time: {result.search_ms:.2f} ms")
    print(f"Total retrieval time: {result.latency_ms:.2f} ms")


def run_ask(
    question: str,
    *,
    top_k: int = 5,
    mode: RetrievalMode = "semantic",
    filters: SearchFilters | None = None,
    max_context_chars: int = 6000,
) -> None:
    """Answer a question using MariaDB retrieval and extractive RAG.

    Args:
        question: Natural-language question.
        top_k: Maximum number of retrieved chunks.
        mode: Semantic or hybrid retrieval mode.
        filters: Optional MariaDB search constraints.
        max_context_chars: Maximum context length.

    Returns:
        None: Prints the answer, citations, and timings.

    Raises:
        WikiRagError: If retrieval or generation fails.
    """
    settings = load_settings()

    with WikiRepository(settings.db) as repo:
        retriever = Retriever(repo, get_embedder())
        generator = ExtractiveGenerator()

        result = answer_question(
            question,
            retriever,
            generator,
            top_k=top_k,
            mode=mode,
            filters=filters,
            max_context_chars=max_context_chars,
        )

    print(f"Question: {result.question}")
    print(f"Retrieval mode: {result.retrieval.mode}")
    print(f"Generator: {result.generator_name}")

    print()
    print("Answer:")
    print(result.answer)

    print()
    print("Sources:")

    # Context sources match the citation numbers in the answer.
    if not result.context.sources:
        print("No supporting sources were retrieved.")

    for number, source in enumerate(result.context.sources, start=1):
        print(f"[{number}] {source.article_title}")
        print(f"    {source.article_url}")
        print(f"    Chunk ID: {source.chunk_id}")

    if result.context.truncated:
        print()
        print("Note: Some retrieved context was excluded by the size limit.")

    print()
    print(f"Retrieved chunks: {len(result.retrieval.hits)}")
    print(f"Retrieval time: {result.retrieval.latency_ms:.2f} ms")
    print(f"Total RAG time: {result.latency_ms:.2f} ms")


def run_evaluate(repeats: int = 5) -> int:
    """Run the existing reproducible retrieval benchmark.

    Args:
        repeats: Measured repetitions per evaluation query.

    Returns:
        int: The benchmark process's exit status.

    Raises:
        ValidationError: If repetitions are invalid or the runner
            script does not exist.
    """
    if type(repeats) is not int or repeats < 1:
        raise ValidationError("--repeats must be a positive integer")

    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "scripts" / "run_retrieval_benchmark.py"

    if not script.is_file():
        raise ValidationError(f"Evaluation script not found: {script}")

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repeats",
            str(repeats),
        ],
        cwd=project_root,
        check=False,
    )

    return completed.returncode


def run_stats(
    *,
    min_category_articles: int = 1,
    show_categories: bool = False,
) -> None:
    """Display article, chunk, topic, and category statistics.

    Args:
        min_category_articles: Minimum number of articles per category.
        show_categories: Whether to print category names.

    Returns:
        None: Prints current MariaDB corpus statistics.

    Raises:
        ValidationError: If the category threshold is invalid.
        WikiRagError: If configuration or database access fails.
    """
    if type(min_category_articles) is not int or min_category_articles < 1:
        raise ValidationError("--min-category-articles must be a positive integer")

    settings = load_settings()

    with WikiRepository(settings.db) as repo:
        articles = repo.count_articles()
        chunks = repo.count_chunks()
        topics = repo.list_topics()
        categories = repo.list_categories(min_articles=min_category_articles)

    print("WikiRAG Database Statistics")
    print(f"Database: {settings.db.database}")
    print(f"Articles: {articles}")
    print(f"Chunks: {chunks}")
    print(f"Topics: {len(topics)}")

    for topic in topics:
        print(f"  - {topic}")

    print(f"Categories (minimum {min_category_articles} articles): {len(categories)}")

    if show_categories:
        for category in categories:
            print(f"  - {category}")

    if articles == 0 or chunks == 0:
        print("Warning: The Wikipedia corpus is empty or incomplete.")


def run_metric_experiment(
    sample_query: str,
    *,
    repeats: int,
    output_path: Path,
) -> None:
    """Run and save the MariaDB distance-metric comparison.

    Args:
        sample_query: Question used to generate the query embedding.
        repeats: Measured executions per SQL variant, at least five.
        output_path: Destination for the JSON report.

    Returns:
        None: Prints experimental measurements and report location.

    Raises:
        ValidationError: If arguments or the destination are invalid.
        WikiRagError: If embedding or database access fails.
        OSError: If the report cannot be written.
    """
    if not isinstance(sample_query, str) or not sample_query.strip():
        raise ValidationError("Experiment query must not be blank")

    if type(repeats) is not int or repeats < 5:
        raise ValidationError("--repeats must be at least 5")

    validate_report_path(output_path)

    print("Loading embedding model...", flush=True)
    embedder = get_embedder()

    print("Running MariaDB metric-mismatch experiment...", flush=True)

    report = run_metric_mismatch(
        embedder,
        sample_query=sample_query,
        repeats=repeats,
        config=load_settings().db,
    )

    saved_path = write_experiment_report(
        report,
        output_path=output_path,
    )

    print()
    print("Metric Mismatch Experiment")
    print(f"MariaDB version: {report['mariadb_version']}")
    print(f"Stored chunks: {report['chunk_count']}")
    print(f"Measured repetitions: {report['repeats']}")

    for name, metrics in report["variants"].items():
        print()
        print(f"Variant: {name}")
        print(f"HNSW index used: {metrics['uses_vector_index']}")
        print(f"Mean latency: {metrics['mean_ms']:.3f} ms")
        print(f"P95 latency: {metrics['p95_ms']:.3f} ms")

    print()
    print(f"Experiment report saved to: {saved_path}")


def run_transaction_experiment(*, output_path: Path) -> None:
    """Run transaction-visibility checks on the isolated test database.

    Args:
        output_path: Destination for the JSON experiment report.

    Returns:
        None: Prints visibility observations and report location.

    Raises:
        ValidationError: If the output is invalid, the selected
            database is unsafe, or the test database is not empty.
        WikiRagError: If database initialization or the experiment fails.
        OSError: If the report cannot be written.
    """
    validate_report_path(output_path)

    settings = load_settings()
    test_database = settings.db_name_test

    # Never allow this experiment to target the application database.
    if not test_database.endswith("_test") or test_database == settings.db.database:
        raise ValidationError("Transaction visibility requires a separate *_test database")

    test_config = replace(
        settings.db,
        database=test_database,
    )

    # Create or verify the test schema without deleting existing tables.
    with closing(get_connection(test_config)) as connection:
        init_schema(connection, recreate=False)

    with WikiRepository(test_config) as repo:
        if repo.count_articles() != 0 or repo.count_chunks() != 0:
            raise ValidationError(
                "Transaction visibility requires an empty test database. "
                "Existing test records will not be deleted automatically."
            )

    print(f"Using isolated test database: {test_database}", flush=True)
    print("Running transaction visibility experiment...", flush=True)

    report = run_transaction_visibility(config=test_config)

    saved_path = write_experiment_report(
        report,
        output_path=output_path,
    )

    print()
    print("Transaction Visibility Experiment")

    for isolation, states in report["isolation_levels"].items():
        print()
        print(f"Isolation level: {isolation}")

        for phase in (
            "uncommitted",
            "after_rollback",
            "after_commit",
            "after_commit_fresh_reader",
            "after_cleanup",
        ):
            observation = states[phase]

            print(
                f"  {phase}: "
                f"articles={observation['articles']}, "
                f"chunks={observation['chunks']}, "
                f"indexed_hits={observation['q1_hits']}, "
                f"exact_hits={observation['exact_hits']}"
            )

    print()
    print(f"Experiment report saved to: {saved_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the requested WikiRAG command.

    Args:
        argv: Optional command-line arguments; uses sys.argv
            when omitted.

    Returns:
        int: Zero on success or a nonzero error status.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init-db":
            run_init_db()

        elif args.command == "build-snapshot":
            run_build_snapshot(args.seed, args.output)

        elif args.command == "ingest":
            return run_ingest(args.snapshot, args.limit)

        elif args.command == "search":
            filters = build_search_filters(args)

            run_search(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                filters=filters,
            )

        elif args.command == "ask":
            filters = build_search_filters(args)

            if args.max_context_chars < 1:
                raise ValidationError("--max-context-chars must be a positive integer")

            run_ask(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                filters=filters,
                max_context_chars=args.max_context_chars,
            )

        elif args.command == "evaluate":
            return run_evaluate(args.repeats)

        elif args.command == "stats":
            run_stats(
                min_category_articles=args.min_category_articles,
                show_categories=args.show_categories,
            )

        elif args.command == "experiment" and args.experiment_name == "metric-mismatch":
            run_metric_experiment(
                args.query,
                repeats=args.repeats,
                output_path=args.output,
            )

        elif args.command == "experiment" and args.experiment_name == "transaction-visibility":
            run_transaction_experiment(output_path=args.output)

    except WikiRagError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
