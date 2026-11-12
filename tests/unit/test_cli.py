"""Test the WikiRAG command-line entry point."""

from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from wikirag import cli
from wikirag.errors import DatabaseConnectionError
from wikirag.models import IngestReport


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
