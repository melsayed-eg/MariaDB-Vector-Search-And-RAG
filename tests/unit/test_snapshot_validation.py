from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validate_snapshot import validate_snapshot


def test_validate_snapshot_aborts_on_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = tmp_path / "wikipedia_snapshot.jsonl"
    seed = tmp_path / "seed_titles.csv"
    seed.write_text("topic,title\nalgorithms,Binary search\n", encoding="utf-8")
    snap.write_text(
        '{"article_id": 1, "title": "Binary search"\n', encoding="utf-8"
    )  # Malformed JSON line

    with patch("scripts.validate_snapshot.Path") as mock_path:

        def path_side_effect(arg: str) -> Path:
            if "snapshot" in arg:
                return snap
            if "seed" in arg:
                return seed
            return Path(arg)

        mock_path.side_effect = path_side_effect
        with pytest.raises(SystemExit) as exc:
            validate_snapshot()
        assert exc.value.code != 0


def test_validate_snapshot_detects_swapped_topic_assignments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = tmp_path / "seed_titles.csv"
    seed.write_text(
        "topic,title\nalgorithms,Binary search\ndatabases,B-tree\n",
        encoding="utf-8",
    )
    snap = tmp_path / "wikipedia_snapshot.jsonl"
    # Swapped: Binary search labeled as databases
    records = [
        {
            "article_id": 1,
            "title": "Binary search",
            "url": "https://en.wikipedia.org/wiki/Binary_search",
            "revision_id": 100,
            "revised_at": "2026-10-30T00:00:00Z",
            "fetched_at": "2026-10-30T00:00:00Z",
            "topic": "databases",  # Mismatch with seed!
            "categories": [],
            "linked_titles": [],
            "text": "Some text content.",
        },
        {
            "article_id": 2,
            "title": "B-tree",
            "url": "https://en.wikipedia.org/wiki/B-tree",
            "revision_id": 101,
            "revised_at": "2026-10-30T00:00:00Z",
            "fetched_at": "2026-10-30T00:00:00Z",
            "topic": "algorithms",  # Mismatch with seed!
            "categories": [],
            "linked_titles": [],
            "text": "Some other text.",
        },
    ]
    snap.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    with patch("scripts.validate_snapshot.Path") as mock_path:

        def path_side_effect(arg: str) -> Path:
            if "snapshot" in arg:
                return snap
            if "seed" in arg:
                return seed
            return Path(arg)

        mock_path.side_effect = path_side_effect
        with pytest.raises(SystemExit) as exc:
            validate_snapshot()
        assert exc.value.code != 0
