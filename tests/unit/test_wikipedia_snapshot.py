"""Unit tests for building and reading Wikipedia snapshots without network access."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from wikirag.errors import ValidationError, WikiRagError
from wikirag.ingestion import wikipedia
from wikirag.ingestion.wikipedia import RawArticle, build_snapshot, load_snapshot

ARTICLE_IDS = {"Black hole": 4223, "DNA": 7955, "Zürich": 34}


def make_article(title: str, article_id: int) -> RawArticle:
    """Build a complete article with fixed times, so files are reproducible."""
    return RawArticle(
        article_id=article_id,
        title=title,
        url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        revision_id=1000 + article_id,
        revised_at=datetime(2026, 9, 30, 8, 15, 0),
        text=f"Text about {title}.",
        fetched_at=datetime(2026, 10, 25, 12, 0, 0),
        categories=("Science",),
        linked_titles=("Star",),
    )


def install_fake_fetch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failing: tuple[str, ...] = (),
    ids: dict[str, int] | None = None,
) -> list[str]:
    """Replace the real download with a fake one and return the list of requested titles."""
    requested: list[str] = []
    article_ids = ids or ARTICLE_IDS

    def fake_fetch(title: str, *, topic: str | None = None, **_: Any) -> RawArticle:
        requested.append(title)
        if title in failing:
            raise WikiRagError(f"cannot fetch {title}")
        return replace(make_article(title, article_ids[title]), topic=topic)

    monkeypatch.setattr(wikipedia, "fetch_article", fake_fetch)
    return requested


def write_seed(tmp_path: Path) -> Path:
    """Write a small seed list and return its path."""
    path = tmp_path / "seed.csv"
    path.write_text("topic,title\nphysics,Black hole\nbiology,DNA\ngeography,Zürich\n", "utf-8")
    return path


def valid_record(**overrides: Any) -> dict[str, Any]:
    """Build one valid snapshot record and apply any overrides."""
    record: dict[str, Any] = {
        "article_id": 4223,
        "title": "Black hole",
        "url": "https://en.wikipedia.org/wiki/Black_hole",
        "revision_id": 5,
        "revised_at": "2026-09-30T08:15:00Z",
        "fetched_at": "2026-10-25T12:00:00Z",
        "topic": "physics",
        "categories": ["Science"],
        "linked_titles": ["Star"],
        "text": "A black hole is a region of spacetime.",
    }
    record.update(overrides)
    return record


def write_lines(tmp_path: Path, *records: dict[str, Any]) -> Path:
    """Write records as a snapshot file and return its path."""
    path = tmp_path / "snapshot.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), "utf-8")
    return path


def test_build_then_load_returns_the_same_articles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_fetch(monkeypatch)
    out_path = tmp_path / "snapshot.jsonl"
    assert build_snapshot(write_seed(tmp_path), out_path, delay_s=0) == 3
    expected = [
        replace(make_article("Black hole", 4223), topic="physics"),
        replace(make_article("DNA", 7955), topic="biology"),
        replace(make_article("Zürich", 34), topic="geography"),
    ]
    assert list(load_snapshot(out_path)) == expected


def test_snapshot_file_is_deterministic_and_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_fetch(monkeypatch)
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    build_snapshot(write_seed(tmp_path), first, delay_s=0)
    build_snapshot(write_seed(tmp_path), second, delay_s=0)
    assert first.read_bytes() == second.read_bytes()
    raw = first.read_text(encoding="utf-8")
    assert "Zürich" in raw
    assert "\\u" not in raw
    lines = raw.splitlines()
    assert len(lines) == 3
    record = json.loads(lines[0])
    assert list(record) == sorted(record)


def test_creates_missing_parent_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_fetch(monkeypatch)
    out_path = tmp_path / "deep" / "folder" / "snapshot.jsonl"
    build_snapshot(write_seed(tmp_path), out_path, delay_s=0)
    assert out_path.is_file()


def test_failed_article_aborts_build_and_preserves_existing_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_file = write_seed(tmp_path)
    out_path = tmp_path / "snapshot.jsonl"
    out_path.write_text("existing content\n", encoding="utf-8")

    install_fake_fetch(monkeypatch, failing=("DNA",))

    with pytest.raises(WikiRagError, match="Snapshot incomplete.*DNA"):
        build_snapshot(seed_file, out_path, delay_s=0)

    # Old snapshot remains untouched
    assert out_path.read_text(encoding="utf-8") == "existing content\n"
    assert not (tmp_path / "snapshot.jsonl.tmp").exists()


def test_duplicate_article_id_aborts_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_fetch(monkeypatch, ids={"Black hole": 1, "DNA": 1, "Zürich": 2})
    out_path = tmp_path / "snapshot.jsonl"
    out_path.write_text("original snapshot\n", encoding="utf-8")

    with pytest.raises(WikiRagError, match="duplicate Wikipedia article id"):
        build_snapshot(write_seed(tmp_path), out_path, delay_s=0)

    assert out_path.read_text(encoding="utf-8") == "original snapshot\n"
    assert not (tmp_path / "snapshot.jsonl.tmp").exists()


def test_nothing_downloaded_raises_and_leaves_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_fetch(monkeypatch, failing=("Black hole", "DNA", "Zürich"))
    out_path = tmp_path / "snapshot.jsonl"
    with pytest.raises(WikiRagError, match="Snapshot incomplete"):
        build_snapshot(write_seed(tmp_path), out_path, delay_s=0)
    assert not out_path.exists()
    assert not (tmp_path / "snapshot.jsonl.tmp").exists()


def test_failed_build_keeps_the_old_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_fetch(monkeypatch, failing=("Black hole", "DNA", "Zürich"))
    out_path = tmp_path / "snapshot.jsonl"
    out_path.write_text("old snapshot", encoding="utf-8")
    with pytest.raises(WikiRagError):
        build_snapshot(write_seed(tmp_path), out_path, delay_s=0)
    assert out_path.read_text(encoding="utf-8") == "old snapshot"


def test_negative_delay_raises_before_any_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = install_fake_fetch(monkeypatch)
    with pytest.raises(ValidationError, match="delay_s"):
        build_snapshot(write_seed(tmp_path), tmp_path / "s.jsonl", delay_s=-1)
    assert requested == []


def test_waits_between_requests_but_not_before_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_fetch(monkeypatch)
    pauses: list[float] = []
    monkeypatch.setattr(wikipedia.time, "sleep", pauses.append)
    build_snapshot(write_seed(tmp_path), tmp_path / "s.jsonl", delay_s=0.5)
    assert pauses == [0.5, 0.5]


def test_invalid_seed_file_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_fetch(monkeypatch)
    bad_seed = tmp_path / "seed.csv"
    bad_seed.write_text("name\nDNA\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="header"):
        build_snapshot(bad_seed, tmp_path / "s.jsonl", delay_s=0)


def test_load_missing_file_raises_immediately(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="not found"):
        load_snapshot(tmp_path / "missing.jsonl")


def test_load_skips_blank_lines_and_accepts_null_topic(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.jsonl"
    path.write_text("\n" + json.dumps(valid_record(topic=None)) + "\n\n", encoding="utf-8")
    articles = list(load_snapshot(path))
    assert len(articles) == 1
    assert articles[0].topic is None


def test_load_reports_the_line_of_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.jsonl"
    path.write_text(json.dumps(valid_record()) + "\n{broken\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="line 2"):
        list(load_snapshot(path))


def test_load_rejects_a_line_that_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.jsonl"
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="JSON object"):
        list(load_snapshot(path))


def test_load_rejects_missing_fields(tmp_path: Path) -> None:
    record = valid_record()
    del record["text"]
    with pytest.raises(ValidationError, match="missing fields: text"):
        list(load_snapshot(write_lines(tmp_path, record)))


@pytest.mark.parametrize(
    "overrides",
    [
        {"article_id": 0},
        {"article_id": "4223"},
        {"revision_id": -1},
        {"title": ""},
        {"url": ""},
        {"text": "   "},
        {"topic": 5},
        {"categories": "Science"},
        {"linked_titles": [1, 2]},
        {"revised_at": "yesterday"},
        {"fetched_at": None},
    ],
)
def test_load_rejects_invalid_values(tmp_path: Path, overrides: dict[str, Any]) -> None:
    path = write_lines(tmp_path, valid_record(**overrides))
    with pytest.raises(ValidationError, match="line 1"):
        list(load_snapshot(path))


def test_load_rejects_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.jsonl"
    path.write_bytes(b"\xff\xfe\n")
    with pytest.raises(ValidationError, match="UTF-8"):
        list(load_snapshot(path))


def test_build_snapshot_rejects_invalid_inputs(tmp_path: Path) -> None:
    seed_file = write_seed(tmp_path)
    out_path = tmp_path / "snapshot.jsonl"

    for invalid_delay in (-1, -0.1, float("nan"), float("inf"), True, False, "0.2"):
        with pytest.raises(ValidationError):
            build_snapshot(seed_file, out_path, delay_s=invalid_delay)  # type: ignore

    with pytest.raises(ValidationError):
        build_snapshot(tmp_path / "non_existent.csv", out_path)


def test_committed_snapshot_integrity() -> None:
    snapshot_path = Path("data/snapshot/wikipedia_snapshot.jsonl")
    assert snapshot_path.is_file(), "Committed snapshot must exist"

    articles = list(load_snapshot(snapshot_path))
    assert len(articles) == 200, f"Expected 200 articles, found {len(articles)}"

    seen_ids = set()
    topic_counts: dict[str, int] = {}
    expected_topics = {
        "algorithms": 35,
        "systems_networks": 35,
        "ai_ml": 30,
        "languages_se": 30,
        "databases": 25,
        "theory_security": 25,
        "history_people": 20,
    }

    for a in articles:
        assert a.article_id > 0
        assert a.article_id not in seen_ids, f"Duplicate article ID: {a.article_id}"
        seen_ids.add(a.article_id)

        assert a.title and a.title.strip()
        assert a.url.startswith("https://en.wikipedia.org/wiki/")
        assert a.revision_id > 0
        assert a.text and len(a.text.strip()) > 0
        assert a.topic in expected_topics

        topic_counts[a.topic] = topic_counts.get(a.topic, 0) + 1

    assert topic_counts == expected_topics
