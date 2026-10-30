"""Validate the Wikipedia snapshot against the seed list and print corpus statistics."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from wikirag.ingestion.chunking import split_into_chunks
from wikirag.ingestion.cleaning import clean_text
from wikirag.ingestion.wikipedia import load_snapshot

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "article_id",
    "title",
    "url",
    "revision_id",
    "revised_at",
    "fetched_at",
    "topic",
    "categories",
    "linked_titles",
    "text",
)


def read_seed_counts(path: Path) -> tuple[Counter[str], set[str]]:
    """Count seed titles per topic.

    Args:
        path: Seed CSV file with a ``topic,title`` header.

    Returns:
        The number of seeds per topic and the set of all seed titles.
    """
    counts: Counter[str] = Counter()
    titles: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            counts[row["topic"]] += 1
            titles.add(row["title"].replace("_", " "))
    return counts, titles


def validate(snapshot: Path, seed: Path) -> tuple[list[str], dict[str, object]]:
    """Check a snapshot file and collect statistics.

    Args:
        snapshot: JSON Lines snapshot to check.
        seed: Seed CSV that the snapshot was built from.

    Returns:
        A list of problems (empty if the snapshot is valid) and a dictionary of statistics.
    """
    problems: list[str] = []
    records = [
        json.loads(line) for line in snapshot.read_text("utf-8").splitlines() if line.strip()
    ]
    # the project loader must accept every record too
    loaded = list(load_snapshot(snapshot))
    if len(loaded) != len(records):
        problems.append("loader and raw reader disagree on the number of records")

    for number, record in enumerate(records, start=1):
        for field in REQUIRED:
            if field not in record or record[field] in (None, ""):
                if field in ("categories", "linked_titles") and record.get(field) == []:
                    continue
                problems.append(f"record {number}: missing or empty {field}")
        if not clean_text(str(record.get("text", ""))):
            problems.append(f"record {number}: text is empty after cleaning")

    for field in ("article_id", "title"):
        counts = Counter(record.get(field) for record in records)
        problems += [f"duplicate {field}: {value}" for value, n in counts.items() if n > 1]

    expected, seed_titles = read_seed_counts(seed)
    actual = Counter(record.get("topic") for record in records)
    for topic in sorted(set(expected) | set(actual)):
        if expected[topic] != actual[topic]:
            problems.append(f"topic {topic}: expected {expected[topic]}, found {actual[topic]}")
    missing = seed_titles - {record.get("title") for record in records}
    problems += [f"seed title not in snapshot: {title}" for title in sorted(missing)]

    titles = {record["title"] for record in records if "title" in record}
    categories = Counter(c for record in records for c in record.get("categories", []))
    link_pairs = {(r["title"], t) for r in records for t in r.get("linked_titles", [])}
    resolved = {pair for pair in link_pairs if pair[1] in titles and pair[1] != pair[0]}
    chunk_sizes = [
        len(chunk.text)
        for record in records
        for chunk in split_into_chunks(clean_text(str(record.get("text", ""))))
    ]
    stats: dict[str, object] = {
        "articles": len(records),
        "articles_per_topic": dict(sorted(actual.items())),
        "distinct_categories": len(categories),
        "category_memberships": sum(categories.values()),
        "distinct_outgoing_links": len(link_pairs),
        "links_resolving_inside_corpus": len(resolved),
        "text_characters": sum(len(str(record.get("text", ""))) for record in records),
        "chunks_default_settings": len(chunk_sizes),
        "chunk_chars_min_max": (min(chunk_sizes), max(chunk_sizes)) if chunk_sizes else None,
        "file_megabytes": round(snapshot.stat().st_size / 1_000_000, 2),
    }
    return problems, stats


def main() -> int:
    """Run the validation and print a report.

    Returns:
        0 if the snapshot is valid, otherwise 1.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot", type=Path, default=ROOT / "data/snapshot/wikipedia_snapshot.jsonl"
    )
    parser.add_argument("--seed", type=Path, default=ROOT / "data/seed_titles.csv")
    arguments = parser.parse_args()
    problems, stats = validate(arguments.snapshot, arguments.seed)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    for problem in problems:
        print("PROBLEM:", problem)
    print("VALID" if not problems else f"INVALID ({len(problems)} problems)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
