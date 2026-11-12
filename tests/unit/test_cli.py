"""Test the WikiRAG command-line entry point."""

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from wikirag import cli
from wikirag.errors import DatabaseConnectionError
from wikirag.models import (
    ContextBundle,
    IngestReport,
    RAGAnswer,
    RetrievalResult,
    SearchFilters,
    SearchHit,
)


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that the CLI displays its available commands."""
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])

    assert result.value.code == 0
    assert "init-db" in capsys.readouterr().out


def test_init_db_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that init-db calls the database setup handler."""
    calls = []

    def fake_init_db() -> None:
        """Record a database initialization request."""
        calls.append(True)

    monkeypatch.setattr(cli, "run_init_db", fake_init_db)

    assert cli.main(["init-db"]) == 0
    assert calls == [True]


def test_init_db_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify that database errors produce a nonzero exit status."""

    def fake_init_db() -> None:
        """Simulate a database connection failure."""
        raise DatabaseConnectionError("Database unavailable")

    monkeypatch.setattr(cli, "run_init_db", fake_init_db)

    assert cli.main(["init-db"]) == 1
    assert "Database unavailable" in capsys.readouterr().err


def test_build_snapshot_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify that the CLI calls the Wikipedia snapshot builder."""
    calls: list[tuple[Path, Path]] = []

    def fake_build_snapshot(seed: Path, output: Path) -> int:
        """Record the snapshot arguments without downloading articles."""
        calls.append((seed, output))
        return 2

    monkeypatch.setattr(cli, "build_snapshot", fake_build_snapshot)

    result = cli.main(
        [
            "build-snapshot",
            "--seed",
            "data/seed_titles.csv",
            "--output",
            "data/snapshot/test.jsonl",
        ]
    )

    assert result == 0
    assert calls == [
        (
            Path("data/seed_titles.csv"),
            Path("data/snapshot/test.jsonl"),
        )
    ]
    assert "2 articles" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("failed", "expected_code"),
    [
        ((), 0),
        ((("Example article", "Test failure"),), 1),
    ],
)
def test_ingest_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failed: tuple[tuple[str, str], ...],
    expected_code: int,
) -> None:
    """Verify ingestion wiring and success or failure exit codes."""
    database_config = object()
    fake_embedder = object()
    fake_repository = object()

    def fake_load_settings() -> SimpleNamespace:
        """Return configuration without accessing local credentials."""
        return SimpleNamespace(db=database_config)

    def fake_get_embedder() -> object:
        """Return an isolated fake embedding component."""
        return fake_embedder

    def fake_repository_factory(config: object) -> AbstractContextManager[object]:
        """Provide a context-managed repository without MariaDB."""
        assert config is database_config
        return nullcontext(fake_repository)

    def fake_ingest_snapshot(
        snapshot_path: Path,
        repo: object,
        embedder: object,
        *,
        limit: int | None = None,
    ) -> IngestReport:
        """Validate command arguments and return a synthetic report."""
        assert snapshot_path == Path("sample.jsonl")
        assert repo is fake_repository
        assert embedder is fake_embedder
        assert limit == 3

        return IngestReport(
            inserted=2,
            updated=0,
            skipped=1,
            failed=failed,
        )

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "get_embedder", fake_get_embedder)
    monkeypatch.setattr(cli, "WikiRepository", fake_repository_factory)
    monkeypatch.setattr(cli, "ingest_snapshot", fake_ingest_snapshot)

    result = cli.main(["ingest", "--snapshot", "sample.jsonl", "--limit", "3"])

    assert result == expected_code

    captured = capsys.readouterr()
    assert "Inserted: 2" in captured.out
    assert "Skipped: 1" in captured.out

    if failed:
        assert "Example article" in captured.err


def test_build_snapshot_requires_output() -> None:
    """Verify that snapshot creation requires an output path."""
    with pytest.raises(SystemExit) as result:
        cli.main(["build-snapshot"])

    assert result.value.code == 2


def test_search_semantic_filters() -> None:
    """Verify semantic search does not require SQL filters."""
    args = cli.build_parser().parse_args(["search", "What is an algorithm?"])

    assert args.mode == "semantic"
    assert args.top_k == 5
    assert cli.build_search_filters(args) is None


def test_search_hybrid_filters() -> None:
    """Verify CLI options produce the shared SearchFilters object."""
    args = cli.build_parser().parse_args(
        [
            "search",
            "What is an algorithm?",
            "--mode",
            "hybrid",
            "--topic",
            "algorithms",
            "--article-id",
            "13995",
            "--min-length-chars",
            "500",
        ]
    )

    filters = cli.build_search_filters(args)

    assert filters is not None
    assert filters.topics == ("algorithms",)
    assert filters.article_ids == (13995,)
    assert filters.min_length_chars == 500


@pytest.mark.parametrize(
    "arguments",
    [
        ["search", "test", "--mode", "hybrid"],
        ["search", "test", "--topic", "algorithms"],
        ["search", "test", "--top-k", "0"],
        [
            "search",
            "test",
            "--mode",
            "hybrid",
            "--article-id",
            "-1",
        ],
        [
            "search",
            "test",
            "--mode",
            "hybrid",
            "--edited-since",
            "not-a-date",
        ],
        [
            "search",
            "test",
            "--mode",
            "hybrid",
            "--edited-since",
            "2026-11-12T12:00:00+01:00",
        ],
    ],
)
def test_search_invalid_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    """Verify invalid search options fail before accessing MariaDB."""

    def fake_run_search(*args: object, **kwargs: object) -> None:
        """Fail if an invalid request reaches retrieval."""
        raise AssertionError("Retrieval must not execute")

    monkeypatch.setattr(cli, "run_search", fake_run_search)

    assert cli.main(arguments) == 1
    assert "Error:" in capsys.readouterr().err


def test_search_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify search CLI arguments reach the retrieval handler."""
    calls: list[tuple[object, ...]] = []

    def fake_run_search(
        query: str,
        *,
        top_k: int,
        mode: str,
        filters: SearchFilters | None,
    ) -> None:
        """Record arguments sent to the search handler."""
        calls.append((query, top_k, mode, filters))

    monkeypatch.setattr(cli, "run_search", fake_run_search)

    result = cli.main(
        [
            "search",
            "How does heapsort work?",
            "--mode",
            "hybrid",
            "--top-k",
            "3",
            "--article-id",
            "13995",
        ]
    )

    assert result == 0
    assert calls == [
        (
            "How does heapsort work?",
            3,
            "hybrid",
            SearchFilters(article_ids=(13995,)),
        )
    ]


def test_run_search_displays_retrieval_results(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify search connects the repository, embedder, and retriever."""
    database_config = object()
    fake_repository = object()
    fake_embedder = object()

    hit = SearchHit(
        chunk_id=1,
        article_id=13995,
        article_title="Heapsort",
        article_url="https://en.wikipedia.org/wiki/Heapsort",
        chunk_index=0,
        section_title=None,
        text="Heapsort is a comparison-based sorting algorithm.",
        distance=0.2,
        score=0.8,
    )

    def fake_load_settings() -> SimpleNamespace:
        """Return isolated test database configuration."""
        return SimpleNamespace(db=database_config)

    def fake_repository_factory(
        config: object,
    ) -> AbstractContextManager[object]:
        """Provide a fake repository without opening MariaDB."""
        assert config is database_config
        return nullcontext(fake_repository)

    def fake_get_embedder() -> object:
        """Return a fake embedding component."""
        return fake_embedder

    def fake_retrieve(
        query: str,
        *,
        top_k: int,
        mode: str,
        filters: SearchFilters | None,
    ) -> RetrievalResult:
        """Return a known retrieval result for the CLI test."""
        assert query == "How does heapsort work?"
        assert top_k == 1
        assert mode == "hybrid"
        assert filters == SearchFilters(article_ids=(13995,))

        return RetrievalResult(
            query=query,
            mode="hybrid",
            top_k=top_k,
            filters=filters,
            hits=(hit,),
            embed_ms=10.0,
            search_ms=5.0,
            latency_ms=15.0,
        )

    def fake_retriever_factory(
        repo: object,
        embedder: object,
    ) -> SimpleNamespace:
        """Verify the retriever receives the correct dependencies."""
        assert repo is fake_repository
        assert embedder is fake_embedder
        return SimpleNamespace(retrieve=fake_retrieve)

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "WikiRepository", fake_repository_factory)
    monkeypatch.setattr(cli, "get_embedder", fake_get_embedder)
    monkeypatch.setattr(cli, "Retriever", fake_retriever_factory)

    cli.run_search(
        "How does heapsort work?",
        top_k=1,
        mode="hybrid",
        filters=SearchFilters(article_ids=(13995,)),
    )

    output = capsys.readouterr().out

    assert "Search mode: hybrid" in output
    assert "Matching chunks: 1" in output
    assert "Heapsort" in output
    assert "https://en.wikipedia.org/wiki/Heapsort" in output
    assert "Total retrieval time: 15.00 ms" in output


def test_ask_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the ask command passes retrieval options to RAG."""
    calls: list[tuple[object, ...]] = []

    def fake_run_ask(
        question: str,
        *,
        top_k: int,
        mode: str,
        filters: SearchFilters | None,
        max_context_chars: int,
    ) -> None:
        """Record the arguments sent to the RAG handler."""
        calls.append((question, top_k, mode, filters, max_context_chars))

    monkeypatch.setattr(cli, "run_ask", fake_run_ask)

    result = cli.main(
        [
            "ask",
            "How does heapsort work?",
            "--mode",
            "hybrid",
            "--article-id",
            "13995",
            "--top-k",
            "3",
            "--max-context-chars",
            "4000",
        ]
    )

    assert result == 0
    assert calls == [
        (
            "How does heapsort work?",
            3,
            "hybrid",
            SearchFilters(article_ids=(13995,)),
            4000,
        )
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        ["ask", "test", "--mode", "hybrid"],
        ["ask", "test", "--topic", "algorithms"],
        ["ask", "test", "--max-context-chars", "0"],
        ["ask", " ", "--max-context-chars", "6000"],
    ],
)
def test_ask_rejects_invalid_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    """Verify invalid RAG options fail before accessing the database."""

    def fake_run_ask(*args: object, **kwargs: object) -> None:
        """Fail if an invalid request reaches the RAG handler."""
        raise AssertionError("RAG handler must not execute")

    monkeypatch.setattr(cli, "run_ask", fake_run_ask)

    assert cli.main(arguments) == 1
    assert "Error:" in capsys.readouterr().err


def test_run_ask_displays_cited_answer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify RAG wiring and cited output without requiring MariaDB."""
    database_config = object()
    fake_repository = object()
    fake_embedder = object()
    fake_retriever = object()
    fake_generator = object()
    filters = SearchFilters(article_ids=(13995,))

    hit = SearchHit(
        chunk_id=42,
        article_id=13995,
        article_title="Heapsort",
        article_url="https://en.wikipedia.org/wiki/Heapsort",
        chunk_index=0,
        section_title=None,
        text="Heapsort uses a binary heap to sort elements.",
        distance=0.2,
        score=0.8,
    )

    def fake_load_settings() -> SimpleNamespace:
        """Provide isolated database configuration."""
        return SimpleNamespace(db=database_config)

    def fake_repository_factory(
        config: object,
    ) -> AbstractContextManager[object]:
        """Return a context-managed fake repository."""
        assert config is database_config
        return nullcontext(fake_repository)

    def fake_get_embedder() -> object:
        """Return a fake embedding component."""
        return fake_embedder

    def fake_retriever_factory(
        repo: object,
        embedder: object,
    ) -> object:
        """Verify the retrieval dependencies."""
        assert repo is fake_repository
        assert embedder is fake_embedder
        return fake_retriever

    def fake_generator_factory() -> object:
        """Return the fake answer generator."""
        return fake_generator

    def fake_answer_question(
        question: str,
        retriever: object,
        generator: object,
        *,
        top_k: int,
        mode: str,
        filters: SearchFilters | None,
        max_context_chars: int,
    ) -> RAGAnswer:
        """Verify RAG arguments and return a cited answer."""
        assert retriever is fake_retriever
        assert generator is fake_generator
        assert question == "How does heapsort work?"
        assert top_k == 1
        assert mode == "hybrid"
        assert filters == SearchFilters(article_ids=(13995,))
        assert max_context_chars == 4000

        retrieval = RetrievalResult(
            query=question,
            mode="hybrid",
            top_k=1,
            filters=filters,
            hits=(hit,),
            embed_ms=2.0,
            search_ms=3.0,
            latency_ms=5.0,
        )

        context = ContextBundle(
            text="[1] Heapsort\nHeapsort uses a binary heap.",
            sources=(hit,),
            truncated=False,
        )

        return RAGAnswer(
            question=question,
            answer="Heapsort uses a binary heap. [1]",
            context=context,
            retrieval=retrieval,
            generator_name="extractive",
            latency_ms=6.0,
        )

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "WikiRepository", fake_repository_factory)
    monkeypatch.setattr(cli, "get_embedder", fake_get_embedder)
    monkeypatch.setattr(cli, "Retriever", fake_retriever_factory)
    monkeypatch.setattr(cli, "ExtractiveGenerator", fake_generator_factory)
    monkeypatch.setattr(cli, "answer_question", fake_answer_question)

    cli.run_ask(
        "How does heapsort work?",
        top_k=1,
        mode="hybrid",
        filters=filters,
        max_context_chars=4000,
    )

    output = capsys.readouterr().out

    assert "Heapsort uses a binary heap. [1]" in output
    assert "Generator: extractive" in output
    assert "[1] Heapsort" in output
    assert "https://en.wikipedia.org/wiki/Heapsort" in output
    assert "Chunk ID: 42" in output
    assert "Total RAG time: 6.00 ms" in output


def test_evaluate_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the CLI forwards repetitions to evaluation."""
    calls: list[int] = []

    def fake_run_evaluate(repeats: int) -> int:
        """Record the requested benchmark repetitions."""
        calls.append(repeats)
        return 0

    monkeypatch.setattr(cli, "run_evaluate", fake_run_evaluate)

    assert cli.main(["evaluate", "--repeats", "2"]) == 0
    assert calls == [2]


def test_evaluate_default_repetitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that evaluation defaults to five repetitions."""
    calls: list[int] = []

    def fake_run_evaluate(repeats: int) -> int:
        """Record the default repetition count."""
        calls.append(repeats)
        return 0

    monkeypatch.setattr(cli, "run_evaluate", fake_run_evaluate)

    assert cli.main(["evaluate"]) == 0
    assert calls == [5]


def test_evaluate_rejects_invalid_repetitions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify that invalid repetitions do not start a benchmark."""
    assert cli.main(["evaluate", "--repeats", "0"]) == 1
    assert "positive integer" in capsys.readouterr().err


def test_evaluate_preserves_benchmark_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a failed benchmark produces a nonzero CLI status."""

    def fake_run_evaluate(repeats: int) -> int:
        """Simulate a failed evaluation command."""
        return 2

    monkeypatch.setattr(cli, "run_evaluate", fake_run_evaluate)

    assert cli.main(["evaluate", "--repeats", "1"]) == 2


def test_stats_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that statistics options reach their handler."""
    calls: list[tuple[int, bool]] = []

    def fake_run_stats(
        *,
        min_category_articles: int,
        show_categories: bool,
    ) -> None:
        """Record the statistics command arguments."""
        calls.append((min_category_articles, show_categories))

    monkeypatch.setattr(cli, "run_stats", fake_run_stats)

    result = cli.main(
        [
            "stats",
            "--min-category-articles",
            "5",
            "--show-categories",
        ]
    )

    assert result == 0
    assert calls == [(5, True)]


def test_stats_command_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify default statistics options."""
    calls: list[tuple[int, bool]] = []

    def fake_run_stats(
        *,
        min_category_articles: int,
        show_categories: bool,
    ) -> None:
        """Record default statistics arguments."""
        calls.append((min_category_articles, show_categories))

    monkeypatch.setattr(cli, "run_stats", fake_run_stats)

    assert cli.main(["stats"]) == 0
    assert calls == [(1, False)]


def test_stats_rejects_invalid_minimum(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify invalid category thresholds fail before database access."""
    assert cli.main(["stats", "--min-category-articles", "0"]) == 1
    assert "positive integer" in capsys.readouterr().err


def test_run_stats_displays_database_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify statistics use repository methods without modifying data."""
    database_config = SimpleNamespace(database="wikirag")

    class FakeRepository:
        """Provide deterministic corpus statistics for testing."""

        def count_articles(self) -> int:
            """Return the article count."""
            return 200

        def count_chunks(self) -> int:
            """Return the embedded chunk count."""
            return 8743

        def list_topics(self) -> list[str]:
            """Return sample Wikipedia topics."""
            return ["algorithms", "databases"]

        def list_categories(
            self,
            *,
            min_articles: int = 1,
        ) -> list[str]:
            """Return sample categories for the requested threshold."""
            assert min_articles == 2
            return ["Computer science", "Sorting algorithms"]

    fake_repository = FakeRepository()

    def fake_load_settings() -> SimpleNamespace:
        """Return isolated application settings."""
        return SimpleNamespace(db=database_config)

    def fake_repository_factory(
        config: object,
    ) -> AbstractContextManager[FakeRepository]:
        """Provide a context-managed fake repository."""
        assert config is database_config
        return nullcontext(fake_repository)

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)
    monkeypatch.setattr(cli, "WikiRepository", fake_repository_factory)

    cli.run_stats(
        min_category_articles=2,
        show_categories=True,
    )

    output = capsys.readouterr().out

    assert "Database: wikirag" in output
    assert "Articles: 200" in output
    assert "Chunks: 8743" in output
    assert "Topics: 2" in output
    assert "algorithms" in output
    assert "databases" in output
    assert "Categories (minimum 2 articles): 2" in output
    assert "Sorting algorithms" in output


def test_metric_experiment_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the CLI forwards metric experiment options."""
    calls: list[tuple[str, int, Path]] = []

    def fake_run_metric_experiment(
        sample_query: str,
        *,
        repeats: int,
        output_path: Path,
    ) -> None:
        """Record experiment arguments without accessing MariaDB."""
        calls.append((sample_query, repeats, output_path))

    monkeypatch.setattr(
        cli,
        "run_metric_experiment",
        fake_run_metric_experiment,
    )

    result = cli.main(
        [
            "experiment",
            "metric-mismatch",
            "--query",
            "How does quicksort work?",
            "--repeats",
            "5",
            "--output",
            "results/experiments/test_metric.json",
        ]
    )

    assert result == 0
    assert calls == [
        (
            "How does quicksort work?",
            5,
            Path("results/experiments/test_metric.json"),
        )
    ]


def test_metric_experiment_rejects_invalid_repeats(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify invalid repetition counts fail before loading the model."""
    result = cli.main(
        [
            "experiment",
            "metric-mismatch",
            "--repeats",
            "4",
            "--output",
            "results/experiments/test_metric.json",
        ]
    )

    assert result == 1
    assert "--repeats must be at least 5" in capsys.readouterr().err


def test_metric_experiment_rejects_existing_report(
    tmp_path: Path,
) -> None:
    """Verify existing experiment results cannot be overwritten."""
    output_path = tmp_path / "existing.json"
    output_path.write_text('{"existing": true}', encoding="utf-8")

    with pytest.raises(cli.ValidationError, match="already exists"):
        cli.run_metric_experiment(
            "How does quicksort work?",
            repeats=5,
            output_path=output_path,
        )

    assert output_path.read_text(encoding="utf-8") == ('{"existing": true}')


def test_metric_experiment_rejects_non_json_output(
    tmp_path: Path,
) -> None:
    """Verify experiment reports require a JSON destination."""
    with pytest.raises(cli.ValidationError, match="JSON"):
        cli.run_metric_experiment(
            "How does quicksort work?",
            repeats=5,
            output_path=tmp_path / "report.txt",
        )


def test_transaction_experiment_command_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the CLI forwards the transaction report path."""
    calls: list[Path] = []

    def fake_run_transaction_experiment(*, output_path: Path) -> None:
        """Record the requested experiment report path."""
        calls.append(output_path)

    monkeypatch.setattr(
        cli,
        "run_transaction_experiment",
        fake_run_transaction_experiment,
    )

    result = cli.main(
        [
            "experiment",
            "transaction-visibility",
            "--output",
            "results/experiments/transaction_test.json",
        ]
    )

    assert result == 0
    assert calls == [Path("results/experiments/transaction_test.json")]


def test_transaction_experiment_rejects_non_json_output(
    tmp_path: Path,
) -> None:
    """Verify transaction experiments require a JSON report path."""
    with pytest.raises(cli.ValidationError, match="JSON"):
        cli.run_transaction_experiment(output_path=tmp_path / "report.txt")


def test_transaction_experiment_preserves_existing_report(
    tmp_path: Path,
) -> None:
    """Verify existing experiment results cannot be overwritten."""
    output_path = tmp_path / "existing.json"
    output_path.write_text('{"saved": true}', encoding="utf-8")

    with pytest.raises(cli.ValidationError, match="already exists"):
        cli.run_transaction_experiment(output_path=output_path)

    assert output_path.read_text(encoding="utf-8") == ('{"saved": true}')


def test_transaction_experiment_rejects_application_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify transaction experiments cannot target the main database."""
    settings = SimpleNamespace(
        db=SimpleNamespace(database="wikirag"),
        db_name_test="wikirag",
    )

    def fake_load_settings() -> SimpleNamespace:
        """Return an intentionally unsafe database configuration."""
        return settings

    monkeypatch.setattr(cli, "load_settings", fake_load_settings)

    with pytest.raises(cli.ValidationError, match="separate"):
        cli.run_transaction_experiment(output_path=tmp_path / "transaction.json")
