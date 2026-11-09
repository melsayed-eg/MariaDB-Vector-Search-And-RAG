"""Integration test: real snapshot articles ingested into MariaDB through the repository."""

import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeEmbedder

from wikirag.config import DbConfig, load_settings
from wikirag.db.connection import get_connection
from wikirag.db.repository import WikiRepository
from wikirag.db.schema import init_schema
from wikirag.errors import ValidationError
from wikirag.ingestion.pipeline import ingest_snapshot

pytestmark = pytest.mark.integration

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "snapshot" / "wikipedia_snapshot.jsonl"
ARTICLE_COUNT = 5


@pytest.fixture
def test_db_config() -> DbConfig:
    """Rebuild the dedicated test database and return its connection settings.

    Returns:
        DbConfig: Connection settings for the test database.

    Raises:
        ValidationError: If the test database name is unsafe.
    """
    settings = load_settings()
    if not settings.db_name_test.endswith("_test") or settings.db_name_test == settings.db.database:
        raise ValidationError("Integration tests require a separate test database")
    config = replace(settings.db, database=settings.db_name_test)
    with closing(get_connection(config)) as conn:
        init_schema(conn, recreate=True)
    return config


@pytest.fixture
def small_snapshot(tmp_path: Path) -> Path:
    """Copy the first real snapshot articles into a temporary file.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Path: Snapshot file with ARTICLE_COUNT articles.
    """
    lines = SNAPSHOT.read_text(encoding="utf-8").splitlines()[:ARTICLE_COUNT]
    path = tmp_path / "small.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_real_articles_are_inserted_then_skipped(
    test_db_config: DbConfig, small_snapshot: Path
) -> None:
    embedder = FakeEmbedder()
    with WikiRepository(test_db_config) as repo:
        first = ingest_snapshot(small_snapshot, repo, embedder)
        assert (first.inserted, first.updated, first.skipped) == (ARTICLE_COUNT, 0, 0)
        assert first.failed == ()
        assert repo.count_articles() == ARTICLE_COUNT
        chunk_count = repo.count_chunks()
        assert chunk_count >= ARTICLE_COUNT

        second = ingest_snapshot(small_snapshot, repo, embedder)
        assert (second.inserted, second.updated, second.skipped) == (0, 0, ARTICLE_COUNT)
        assert repo.count_chunks() == chunk_count


def test_article_metadata_is_stored(test_db_config: DbConfig, small_snapshot: Path) -> None:
    first_record = json.loads(small_snapshot.read_text(encoding="utf-8").splitlines()[0])
    with WikiRepository(test_db_config) as repo:
        ingest_snapshot(small_snapshot, repo, FakeEmbedder())
        stored = repo.get_article(first_record["article_id"])
    assert stored is not None
    assert stored.title == first_record["title"]
    assert stored.topic == first_record["topic"]
    assert stored.revision_id == first_record["revision_id"]
    assert len(stored.fingerprint) == 64
    assert set(stored.categories) == set(first_record["categories"])


def test_changed_text_updates_only_that_article(
    test_db_config: DbConfig, small_snapshot: Path, tmp_path: Path
) -> None:
    embedder = FakeEmbedder()
    lines = small_snapshot.read_text(encoding="utf-8").splitlines()
    changed = json.loads(lines[0])
    changed["text"] += "\n\nA new closing sentence added for this test."
    lines[0] = json.dumps(changed, ensure_ascii=False, sort_keys=True)
    changed_path = tmp_path / "changed.jsonl"
    changed_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with WikiRepository(test_db_config) as repo:
        ingest_snapshot(small_snapshot, repo, embedder)
        report = ingest_snapshot(changed_path, repo, embedder)
    assert (report.inserted, report.updated, report.skipped) == (0, 1, ARTICLE_COUNT - 1)
