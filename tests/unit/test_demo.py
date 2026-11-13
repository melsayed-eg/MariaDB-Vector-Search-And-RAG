"""Unit tests for the read-only WikiRAG demonstration."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from scripts import run_demo


class FakeDemoRepository:
    """Provide deterministic database metadata for demo tests."""

    def __init__(
        self,
        *,
        articles: int = 200,
        chunks: int = 8743,
        heapsort_title: str | None = "Heapsort",
    ) -> None:
        """Initialize fake corpus statistics.

        Args:
            articles: Number of stored articles.
            chunks: Number of stored chunks.
            heapsort_title: Expected article title or None if missing.
        """
        self.articles = articles
        self.chunks = chunks
        self.heapsort_title = heapsort_title

    def count_articles(self) -> int:
        """Return the fake article count."""
        return self.articles

    def count_chunks(self) -> int:
        """Return the fake chunk count."""
        return self.chunks

    def get_article(self, article_id: int) -> SimpleNamespace | None:
        """Return the fake Heapsort article if available.

        Args:
            article_id: Requested Wikipedia article identifier.

        Returns:
            SimpleNamespace | None: Article metadata or None.
        """
        assert article_id == run_demo.HEAPSORT_ARTICLE_ID

        if self.heapsort_title is None:
            return None

        return SimpleNamespace(title=self.heapsort_title)


def patch_demo_repository(
    monkeypatch: pytest.MonkeyPatch,
    repository: FakeDemoRepository,
) -> None:
    """Replace database access with a fake repository.

    Args:
        monkeypatch: Pytest fixture for replacing dependencies.
        repository: Fake repository used during the test.

    Returns:
        None: Database access is replaced with isolated test data.
    """
    database_config = object()

    def fake_load_settings() -> SimpleNamespace:
        """Return fake database configuration."""
        return SimpleNamespace(db=database_config)

    def fake_repository_factory(
        config: object,
    ) -> nullcontext[FakeDemoRepository]:
        """Return the fake repository as a context manager."""
        assert config is database_config
        return nullcontext(repository)

    monkeypatch.setattr(run_demo, "load_settings", fake_load_settings)
    monkeypatch.setattr(
        run_demo,
        "WikiRepository",
        fake_repository_factory,
    )


def test_demo_accepts_complete_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the preflight accepts the complete Wikipedia dataset."""
    patch_demo_repository(monkeypatch, FakeDemoRepository())

    assert run_demo.verify_demo_corpus() == (200, 8743)


def test_demo_rejects_incomplete_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify incomplete datasets fail before searching."""
    patch_demo_repository(
        monkeypatch,
        FakeDemoRepository(articles=3, chunks=166),
    )

    with pytest.raises(RuntimeError, match="complete Wikipedia corpus"):
        run_demo.verify_demo_corpus()


def test_demo_rejects_missing_heapsort_article(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the hybrid example requires its expected article."""
    patch_demo_repository(
        monkeypatch,
        FakeDemoRepository(heapsort_title=None),
    )

    with pytest.raises(RuntimeError, match="Heapsort article"):
        run_demo.verify_demo_corpus()


def test_demo_runs_existing_cli_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify all demo steps reuse existing CLI commands."""
    commands: list[tuple[str, ...]] = []

    def fake_verify_demo_corpus() -> tuple[int, int]:
        """Return valid corpus statistics without accessing MariaDB."""
        return 200, 8743

    def fake_cli_main(arguments: tuple[str, ...]) -> int:
        """Record a CLI command and simulate success."""
        commands.append(arguments)
        return 0

    monkeypatch.setattr(
        run_demo,
        "verify_demo_corpus",
        fake_verify_demo_corpus,
    )
    monkeypatch.setattr(run_demo.cli, "main", fake_cli_main)

    assert run_demo.main() == 0
    assert commands == [arguments for _, arguments in run_demo.DEMO_STEPS]
    assert len(commands) == 4


def test_demo_stops_after_failed_cli_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the demonstration stops if an existing CLI command fails."""
    commands: list[tuple[str, ...]] = []

    def fake_verify_demo_corpus() -> tuple[int, int]:
        """Provide valid preflight statistics."""
        return 200, 8743

    def fake_cli_main(arguments: tuple[str, ...]) -> int:
        """Fail on the second command."""
        commands.append(arguments)
        return 2 if len(commands) == 2 else 0

    monkeypatch.setattr(
        run_demo,
        "verify_demo_corpus",
        fake_verify_demo_corpus,
    )
    monkeypatch.setattr(run_demo.cli, "main", fake_cli_main)

    assert run_demo.main() == 2
    assert len(commands) == 2
