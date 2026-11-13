"""End-to-end CLI workflow verification using isolated MariaDB."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeEmbedder

from wikirag import cli
from wikirag.config import DbConfig, load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "snapshot" / "wikipedia_snapshot.jsonl"


@pytest.fixture
def isolated_cli_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[DbConfig]:
    """Prepare an isolated database for the complete CLI workflow.

    Args:
        monkeypatch: Pytest dependency replacement fixture.

    Yields:
        DbConfig: Connection settings for the dedicated test database.

    Raises:
        RuntimeError: If the test database is not safely isolated.
    """
    settings = load_settings()

    if not settings.db_name_test.endswith("_test") or settings.db_name_test == settings.db.database:
        raise RuntimeError("End-to-end tests require an isolated *_test database")

    config = replace(
        settings.db,
        database=settings.db_name_test,
    )

    # Only the authorized test database may be recreated.
    with closing(get_connection(config)) as connection:
        init_schema(connection, recreate=True)

    def fake_cli_settings():
        """Redirect CLI database access to the isolated test database."""
        return replace(settings, db=config)

    monkeypatch.setattr(cli, "load_settings", fake_cli_settings)
    monkeypatch.setattr(cli, "get_embedder", FakeEmbedder)

    try:
        yield config
    finally:
        # Remove test records even when the workflow assertion fails.
        with closing(get_connection(config)) as connection:
            init_schema(connection, recreate=True)


def test_complete_cli_workflow(
    isolated_cli_database: DbConfig,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Verify ingestion, semantic search, hybrid search and cited RAG.

    Args:
        isolated_cli_database: Isolated MariaDB connection configuration.
        tmp_path: Temporary folder for the small test snapshot.
        capsys: Fixture that captures printed CLI output.

    Returns:
        None: Assertions verify each application stage.
    """
    with SNAPSHOT.open(encoding="utf-8") as source:
        article = json.loads(next(source))

    # Keep real Wikipedia metadata but use a short deterministic test text.
    article["text"] = (
        f"{article['title']} is a topic in computer science. "
        f"This article explains {article['title']} and its applications. "
        "Wikipedia articles can be indexed and retrieved with MariaDB."
    )

    snapshot_path = tmp_path / "e2e_snapshot.jsonl"
    snapshot_path.write_text(
        json.dumps(article, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    article_id = int(article["article_id"])

    assert cli.main(["init-db"]) == 0
    capsys.readouterr()

    assert cli.main(["ingest", "--snapshot", str(snapshot_path)]) == 0
    ingestion_output = capsys.readouterr().out

    assert "Inserted: 1" in ingestion_output
    assert "Failed: 0" in ingestion_output

    with WikiRepository(isolated_cli_database) as repo:
        assert repo.count_articles() == 1
        assert repo.count_chunks() >= 1
        assert repo.get_article(article_id) is not None

    assert cli.main(["stats"]) == 0
    statistics_output = capsys.readouterr().out

    assert "Articles: 1" in statistics_output

    assert (
        cli.main(
            [
                "search",
                str(article["title"]),
                "--top-k",
                "1",
            ]
        )
        == 0
    )
    semantic_output = capsys.readouterr().out

    assert "Search mode: semantic" in semantic_output
    assert "Matching chunks: 1" in semantic_output
    assert f"Article ID: {article_id}" in semantic_output

    assert (
        cli.main(
            [
                "search",
                str(article["title"]),
                "--mode",
                "hybrid",
                "--article-id",
                str(article_id),
                "--top-k",
                "1",
            ]
        )
        == 0
    )
    hybrid_output = capsys.readouterr().out

    assert "Search mode: hybrid" in hybrid_output
    assert "Matching chunks: 1" in hybrid_output
    assert f"Article ID: {article_id}" in hybrid_output

    assert (
        cli.main(
            [
                "ask",
                f"What is {article['title']}?",
                "--top-k",
                "1",
            ]
        )
        == 0
    )
    rag_output = capsys.readouterr().out

    assert "Generator: extractive" in rag_output
    assert "Answer:" in rag_output
    assert "Sources:" in rag_output
    assert "[1]" in rag_output
    assert article["url"] in rag_output
