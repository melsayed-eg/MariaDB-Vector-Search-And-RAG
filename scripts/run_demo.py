"""Demonstrate WikiRAG semantic search, hybrid SQL, and cited RAG."""

from __future__ import annotations

import sys

from wikirag import cli
from wikirag.config import load_settings
from wikirag.db.repository import WikiRepository
from wikirag.errors import WikiRagError

EXPECTED_ARTICLES = 200
EXPECTED_CHUNKS = 8743
HEAPSORT_ARTICLE_ID = 13995

DEMO_STEPS = (
    (
        "Wikipedia corpus statistics",
        ("stats",),
    ),
    (
        "Native semantic vector search",
        (
            "search",
            "How does quicksort work?",
            "--top-k",
            "3",
        ),
    ),
    (
        "Hybrid vector search with a relational SQL filter",
        (
            "search",
            "How does heapsort work?",
            "--mode",
            "hybrid",
            "--article-id",
            str(HEAPSORT_ARTICLE_ID),
            "--top-k",
            "3",
        ),
    ),
    (
        "Retrieval-augmented answer with citations",
        (
            "ask",
            "How does quicksort work?",
            "--top-k",
            "5",
        ),
    ),
)


def verify_demo_corpus() -> tuple[int, int]:
    """Verify that the expected Wikipedia demo corpus is available.

    Returns:
        tuple[int, int]: Verified article and chunk counts.

    Raises:
        RuntimeError: If the corpus counts are unexpected or the
            Heapsort article required by the hybrid demo is missing.
        WikiRagError: If configuration or MariaDB access fails.
    """
    settings = load_settings()

    with WikiRepository(settings.db) as repo:
        articles = repo.count_articles()
        chunks = repo.count_chunks()
        heapsort = repo.get_article(HEAPSORT_ARTICLE_ID)

    # Require the complete reproducible dataset used by evaluation.
    if (articles, chunks) != (EXPECTED_ARTICLES, EXPECTED_CHUNKS):
        raise RuntimeError(
            "The demo requires the complete Wikipedia corpus: "
            f"{EXPECTED_ARTICLES} articles and {EXPECTED_CHUNKS} chunks. "
            f"Found {articles} articles and {chunks} chunks. "
            "Run 'make setup' first."
        )

    # Prevent the hybrid example from silently targeting a missing article.
    if heapsort is None or heapsort.title.casefold() != "heapsort":
        raise RuntimeError(
            "The required Heapsort article is missing or has unexpected "
            f"metadata (article ID {HEAPSORT_ARTICLE_ID})."
        )

    return articles, chunks


def main() -> int:
    """Run the read-only demonstration using the existing WikiRAG CLI.

    Returns:
        int: Zero if all demo commands complete, otherwise nonzero.
    """
    try:
        articles, chunks = verify_demo_corpus()
    except (WikiRagError, RuntimeError) as error:
        print(f"Demo preparation failed: {error}", file=sys.stderr)
        return 1

    print("WikiRAG — MariaDB Native Vector Search and RAG", flush=True)
    print(f"Verified corpus: {articles} articles, {chunks} chunks", flush=True)
    print("This demonstration does not modify database records.", flush=True)

    for number, (heading, arguments) in enumerate(DEMO_STEPS, start=1):
        print()
        print(f"Step {number}: {heading}", flush=True)
        print("-" * 60, flush=True)

        # Invoke the same command handlers exposed to normal CLI users.
        status = cli.main(arguments)

        if status != 0:
            print(
                f"Demo stopped: step {number} returned status {status}.",
                file=sys.stderr,
            )
            return status

    print()
    print("WikiRAG demonstration completed successfully.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
