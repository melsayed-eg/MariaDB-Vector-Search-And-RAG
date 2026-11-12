"""Test the WikiRAG command-line entry point."""

import pytest

from wikirag import cli
from wikirag.errors import DatabaseConnectionError


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
