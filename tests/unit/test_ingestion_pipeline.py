"""Unit tests for the ingestion pipeline using in-memory fakes."""

import json
from pathlib import Path

from tests.fakes import FakeEmbedder, InMemoryRepository
from wikirag.ingestion.pipeline import compute_fingerprint, ingest_snapshot


def test_compute_fingerprint_deterministic() -> None:
    fp1 = compute_fingerprint(
        "Sample text", max_chars=1000, overlap_chars=150, model_name="test-model"
    )
    fp2 = compute_fingerprint(
        "Sample text", max_chars=1000, overlap_chars=150, model_name="test-model"
    )
    assert fp1 == fp2
    assert len(fp1) == 64


def test_ingest_snapshot_idempotent(tmp_path: Path) -> None:
    repo = InMemoryRepository()
    embedder = FakeEmbedder()

    # Create a small valid test snapshot with UTC timestamps ending in 'Z'
    snapshot_path = tmp_path / "test_snapshot.jsonl"
    record = {
        "article_id": 101,
        "title": "Relational database",
        "url": "https://en.wikipedia.org/wiki/Relational_database",
        "revision_id": 9999,
        "revised_at": "2026-01-01T00:00:00Z",
        "fetched_at": "2026-01-02T00:00:00Z",
        "topic": "databases",
        "categories": ["Databases"],
        "linked_titles": ["SQL"],
        "text": "A relational database organizes data into tables of rows and columns.",
    }
    snapshot_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    # First run: inserts article
    r1 = ingest_snapshot(snapshot_path, repo, embedder)
    assert r1.inserted == 1
    assert r1.skipped == 0
    assert len(r1.failed) == 0

    # Second run: unchanged article is skipped without re-embedding
    r2 = ingest_snapshot(snapshot_path, repo, embedder)
    assert r2.inserted == 0
    assert r2.skipped == 1
    assert len(r2.failed) == 0
