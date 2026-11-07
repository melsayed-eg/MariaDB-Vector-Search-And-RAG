"""Unit tests for ingest_snapshot and compute_fingerprint using the fakes."""

import json
from pathlib import Path

import pytest
from fakes import FakeEmbedder, InMemoryRepository

from wikirag.errors import SchemaMismatchError, ValidationError, WikiRagError
from wikirag.ingestion.pipeline import compute_fingerprint, ingest_snapshot


def _record(article_id: int, title: str, text: str) -> dict[str, object]:
    return {
        "article_id": article_id,
        "title": title,
        "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
        "revision_id": 10 + article_id,
        "revised_at": "2026-01-01T00:00:00Z",
        "fetched_at": "2026-10-30T00:00:00Z",
        "topic": "algorithms",
        "categories": ["Category A"],
        "linked_titles": ["Other"],
        "text": text,
    }


def _write(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


LONG = "Sorting arranges items in order. " * 80


def test_first_run_inserts_then_second_run_skips(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "A", LONG), _record(2, "B", LONG)])
    repo, embedder = InMemoryRepository(), FakeEmbedder()

    first = ingest_snapshot(snap, repo, embedder)
    assert (first.inserted, first.updated, first.skipped, first.failed) == (2, 0, 0, ())
    chunk_count = repo.count_chunks()
    assert chunk_count > 2

    second = ingest_snapshot(snap, repo, embedder)
    assert (second.inserted, second.updated, second.skipped) == (0, 0, 2)
    assert repo.count_chunks() == chunk_count


def test_unchanged_article_is_not_embedded_again(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "A", LONG)])
    repo = InMemoryRepository()
    ingest_snapshot(snap, repo, FakeEmbedder())

    class CountingEmbedder(FakeEmbedder):
        calls = 0

        def embed_texts(self, texts, *, batch_size=32):  # type: ignore[no-untyped-def]
            CountingEmbedder.calls += 1
            return super().embed_texts(texts, batch_size=batch_size)

    ingest_snapshot(snap, repo, CountingEmbedder())
    assert CountingEmbedder.calls == 0


def test_changed_text_is_updated(tmp_path: Path) -> None:
    repo, embedder = InMemoryRepository(), FakeEmbedder()
    ingest_snapshot(_write(tmp_path / "a.jsonl", [_record(1, "A", LONG)]), repo, embedder)
    report = ingest_snapshot(
        _write(tmp_path / "b.jsonl", [_record(1, "A", LONG + "New sentence here.")]),
        repo,
        embedder,
    )
    assert (report.inserted, report.updated, report.skipped) == (0, 1, 0)


def test_changed_chunk_settings_trigger_update(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "A", LONG)])
    repo, embedder = InMemoryRepository(), FakeEmbedder()
    ingest_snapshot(snap, repo, embedder)
    report = ingest_snapshot(snap, repo, embedder, max_chars=500, overlap_chars=75)
    assert report.updated == 1


def test_empty_article_is_reported_and_run_continues(tmp_path: Path) -> None:
    snap = _write(
        tmp_path / "s.jsonl",
        [_record(1, "Empty", "\u200b\u200b"), _record(2, "Good", LONG)],
    )
    report = ingest_snapshot(snap, InMemoryRepository(), FakeEmbedder())
    assert report.inserted == 1
    assert [title for title, _ in report.failed] == ["Empty"]


def test_repository_failure_is_recorded_and_run_continues(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "Bad", LONG), _record(2, "Good", LONG)])
    repo = InMemoryRepository()
    original = repo.ingest_article

    def flaky(article, chunks):  # type: ignore[no-untyped-def]
        if article.title == "Bad":
            raise WikiRagError("database failure")
        return original(article, chunks)

    repo.ingest_article = flaky  # type: ignore[method-assign]
    report = ingest_snapshot(snap, repo, FakeEmbedder())
    assert report.inserted == 1
    assert report.failed == (("Bad", "database failure"),)


def test_resolve_links_called_once(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "A", LONG), _record(2, "B", LONG)])
    repo = InMemoryRepository()
    calls: list[int] = []
    original = repo.resolve_links
    repo.resolve_links = lambda: (calls.append(1), original())[1]  # type: ignore[method-assign]
    ingest_snapshot(snap, repo, FakeEmbedder())
    assert calls == [1]


def test_limit_processes_only_first_articles(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(i, f"T{i}", LONG) for i in range(1, 4)])
    repo = InMemoryRepository()
    assert ingest_snapshot(snap, repo, FakeEmbedder(), limit=2).inserted == 2
    assert repo.count_articles() == 2


def test_embedding_model_mismatch_is_rejected(tmp_path: Path) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "A", LONG)])
    repo = InMemoryRepository()
    ingest_snapshot(snap, repo, FakeEmbedder())
    with pytest.raises(SchemaMismatchError):
        ingest_snapshot(snap, repo, FakeEmbedder(model_name="other-model"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chars": 0},
        {"max_chars": True},
        {"overlap_chars": -1},
        {"max_chars": 100, "overlap_chars": 100},
        {"limit": 0},
        {"limit": "2"},
    ],
)
def test_invalid_settings_rejected(tmp_path: Path, kwargs: dict[str, object]) -> None:
    snap = _write(tmp_path / "s.jsonl", [_record(1, "A", LONG)])
    with pytest.raises(ValidationError):
        ingest_snapshot(snap, InMemoryRepository(), FakeEmbedder(), **kwargs)  # type: ignore[arg-type]


def test_damaged_snapshot_raises_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        ingest_snapshot(path, InMemoryRepository(), FakeEmbedder())


def test_fingerprint_is_stable_and_sensitive() -> None:
    base = {"max_chars": 1000, "overlap_chars": 150, "model_name": "m"}
    first = compute_fingerprint("text", **base)
    assert first == compute_fingerprint("text", **base)
    assert len(first) == 64
    assert first != compute_fingerprint("text2", **base)
    assert first != compute_fingerprint("text", **{**base, "max_chars": 900})
    assert first != compute_fingerprint("text", **{**base, "overlap_chars": 100})
    assert first != compute_fingerprint("text", **{**base, "model_name": "n"})


def test_fingerprint_parts_do_not_run_together() -> None:
    a = compute_fingerprint("x", max_chars=11, overlap_chars=5, model_name="m")
    b = compute_fingerprint("x", max_chars=1, overlap_chars=15, model_name="m")
    assert a != b


@pytest.mark.parametrize("text", ["", None, 5])
def test_fingerprint_rejects_bad_text(text: object) -> None:
    with pytest.raises(ValidationError):
        compute_fingerprint(text, max_chars=1000, overlap_chars=150, model_name="m")  # type: ignore[arg-type]
