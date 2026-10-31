"""Independent audit validation for local Wikipedia Snapshot JSONL."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from wikirag.errors import ValidationError, WikiRagError
from wikirag.ingestion.wikipedia import load_seed_titles, load_snapshot

EXPECTED_COUNTS = {
    "algorithms": 35,
    "systems_networks": 35,
    "ai_ml": 30,
    "languages_se": 30,
    "databases": 25,
    "theory_security": 25,
    "history_people": 20,
}


def validate_snapshot() -> None:
    """Audit snapshot format, mapping integrity, and topic completeness."""
    snapshot_path = Path("data/snapshot/wikipedia_snapshot.jsonl")
    seed_path = Path("data/seed_titles.csv")

    if not snapshot_path.is_file():
        print(f"Error: Snapshot file missing ({snapshot_path})", file=sys.stderr)
        sys.exit(1)

    try:
        seeds = {title: topic for topic, title in load_seed_titles(seed_path)}
    except (ValidationError, OSError) as err:
        print(f"Error: Could not load baseline seed titles ({err})", file=sys.stderr)
        sys.exit(1)

    seen_ids: set[int] = set()
    seen_titles: set[str] = set()
    actual_counts = {t: 0 for t in EXPECTED_COUNTS}

    try:
        articles = list(load_snapshot(snapshot_path))
    except (ValidationError, WikiRagError, json.JSONDecodeError) as err:
        print(f"Error: Snapshot validation failed: {err}", file=sys.stderr)
        sys.exit(1)

    for idx, art in enumerate(articles, start=1):
        if not art.article_id or not art.title or not art.topic or not art.text:
            print(
                f"Error: Line {idx} is missing required fields (ID: {art.article_id}, Title: {art.title!r})",
                file=sys.stderr,
            )
            sys.exit(1)

        if art.title not in seeds:
            print(
                f"Error: Snapshot title {art.title!r} is not in seed_titles.csv.",
                file=sys.stderr,
            )
            sys.exit(1)

        expected_topic = seeds[art.title]
        if art.topic != expected_topic:
            print(
                f"Error: Mapped topic mismatch for {art.title!r}. Expected {expected_topic!r}, found {art.topic!r}",
                file=sys.stderr,
            )
            sys.exit(1)

        if art.article_id in seen_ids:
            print(
                f"Error: Duplicate Article ID {art.article_id} encountered.",
                file=sys.stderr,
            )
            sys.exit(1)
        seen_ids.add(art.article_id)

        if art.title in seen_titles:
            print(f"Error: Duplicate title {art.title!r} in snapshot.", file=sys.stderr)
            sys.exit(1)
        seen_titles.add(art.title)

        actual_counts[art.topic] += 1

    if len(seen_ids) != 200:
        print(f"Error: Expected 200 articles, but found {len(seen_ids)}.", file=sys.stderr)
        sys.exit(1)

    for topic, expected in EXPECTED_COUNTS.items():
        if actual_counts[topic] != expected:
            print(
                f"Error: Mismatch in {topic!r}. Expected {expected}, got {actual_counts[topic]}.",
                file=sys.stderr,
            )
            sys.exit(1)

    print(
        json.dumps(
            {
                "articles": len(seen_ids),
                "articles_per_topic": actual_counts,
                "file_megabytes": round(snapshot_path.stat().st_size / (1024 * 1024), 2),
            },
            indent=2,
        )
    )
    print("VALID")


if __name__ == "__main__":
    validate_snapshot()
