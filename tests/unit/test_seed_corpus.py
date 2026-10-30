"""Check that the committed seed list matches the planned Computer Science corpus."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from wikirag.ingestion.wikipedia import load_seed_titles

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_COUNTS = {
    "algorithms": 35,
    "languages_se": 30,
    "databases": 25,
    "systems_networks": 35,
    "ai_ml": 30,
    "theory_security": 25,
    "history_people": 20,
}


def test_seed_file_matches_the_planned_topic_counts() -> None:
    seeds = load_seed_titles(REPO_ROOT / "data" / "seed_titles.csv")
    assert dict(Counter(topic for topic, _ in seeds)) == EXPECTED_COUNTS
    assert len(seeds) == 200
