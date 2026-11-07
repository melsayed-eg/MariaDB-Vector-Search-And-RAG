"""Unit tests for the file safety of build_snapshot."""

from datetime import datetime
from pathlib import Path

import pytest

from wikirag.errors import ValidationError, WikiRagError
from wikirag.ingestion import wikipedia
from wikirag.ingestion.wikipedia import RawArticle, build_snapshot, load_snapshot

SEED_TEXT = "topic,title\nalgorithms,Sorting algorithm\ndatabases,Relational database\n"
OLD_SNAPSHOT = "previous valid snapshot\n"


def _article(title: str, topic: str | None, article_id: int) -> RawArticle:
    """Build a small fake article for the patched downloader."""
    return RawArticle(
        article_id=article_id,
        title=title,
        url="https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
        revision_id=100 + article_id,
        revised_at=datetime(2026, 1, 1),
        text=f"Text about {title}.",
        fetched_at=datetime(2026, 10, 30),
        topic=topic,
    )


@pytest.fixture
def seed_file(tmp_path: Path) -> Path:
    """Create a two-article seed file."""
    path = tmp_path / "seeds.csv"
    path.write_text(SEED_TEXT, encoding="utf-8")
    return path


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, ids: dict[str, int]) -> list[str]:
    """Replace fetch_article with a fake; return the list of titles it was asked for."""
    calls: list[str] = []

    def fake_fetch(title: str, *, topic: str | None = None, session: object = None) -> RawArticle:
        calls.append(title)
        if title not in ids:
            raise WikiRagError("download failed")
        return _article(title, topic, ids[title])

    monkeypatch.setattr(wikipedia, "fetch_article", fake_fetch)
    return calls


def test_identical_paths_are_rejected_before_any_download(
    seed_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_fetch(monkeypatch, {"Sorting algorithm": 1, "Relational database": 2})

    with pytest.raises(ValidationError, match="different"):
        build_snapshot(seed_file, seed_file, delay_s=0)

    assert calls == []
    assert seed_file.read_text(encoding="utf-8") == SEED_TEXT


def test_successful_build_replaces_existing_output(
    seed_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetch(monkeypatch, {"Sorting algorithm": 1, "Relational database": 2})
    out_path = tmp_path / "snapshot.jsonl"
    out_path.write_text(OLD_SNAPSHOT, encoding="utf-8")

    assert build_snapshot(seed_file, out_path, delay_s=0) == 2

    articles = list(load_snapshot(out_path))
    assert [a.title for a in articles] == ["Sorting algorithm", "Relational database"]
    assert [a.topic for a in articles] == ["algorithms", "databases"]
    # only the snapshot and the seed file remain; no temporary files
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seeds.csv", "snapshot.jsonl"]


def test_failed_download_keeps_previous_snapshot_and_cleans_up(
    seed_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the second seed is missing from the fake, so its download fails
    _patch_fetch(monkeypatch, {"Sorting algorithm": 1})
    out_path = tmp_path / "snapshot.jsonl"
    out_path.write_text(OLD_SNAPSHOT, encoding="utf-8")

    with pytest.raises(WikiRagError, match="Relational database"):
        build_snapshot(seed_file, out_path, delay_s=0)

    assert out_path.read_text(encoding="utf-8") == OLD_SNAPSHOT
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seeds.csv", "snapshot.jsonl"]


def test_duplicate_page_ids_abort_and_leave_no_output(
    seed_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_fetch(monkeypatch, {"Sorting algorithm": 7, "Relational database": 7})
    out_path = tmp_path / "snapshot.jsonl"

    with pytest.raises(WikiRagError, match="duplicate"):
        build_snapshot(seed_file, out_path, delay_s=0)

    assert not out_path.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["seeds.csv"]


def test_output_path_that_is_a_directory_is_rejected(
    seed_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _patch_fetch(monkeypatch, {"Sorting algorithm": 1, "Relational database": 2})

    with pytest.raises(ValidationError, match="directory"):
        build_snapshot(seed_file, tmp_path, delay_s=0)

    assert calls == []
