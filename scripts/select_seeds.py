"""Verify candidate Wikipedia titles with the MediaWiki API and write the final seed list."""

from __future__ import annotations

import csv
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = (
    "WikiRAG-student-project/0.1 (https://github.com/melsayed-eg/MariaDB-Vector-Search-And-RAG)"
)
ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "data" / "seed_candidates.csv"
OUTPUT = ROOT / "data" / "seed_titles.csv"
TARGETS = {
    "algorithms": 35,
    "languages_se": 30,
    "databases": 25,
    "systems_networks": 35,
    "ai_ml": 30,
    "theory_security": 25,
    "history_people": 20,
}
BATCH_SIZE = 50
MIN_LENGTH_BYTES = 4000


def read_candidates(path: Path) -> list[tuple[str, str]]:
    """Read ``topic,title`` rows from the candidate file.

    Args:
        path: CSV file with a ``topic,title`` header.

    Returns:
        The rows in file order.

    Raises:
        ValueError: If a topic is unknown or a row is malformed.
    """
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        if next(reader, None) != ["topic", "title"]:
            raise ValueError("Candidate file must start with the header topic,title")
        for number, row in enumerate(reader, start=2):
            if len(row) != 2 or not row[0].strip() or not row[1].strip():
                raise ValueError(f"Line {number}: expected topic,title")
            topic, title = row[0].strip(), row[1].strip().replace("_", " ")
            if topic not in TARGETS:
                raise ValueError(f"Line {number}: unknown topic {topic!r}")
            rows.append((topic, title))
    return rows


def lookup(titles: list[str], session: requests.Session) -> dict[str, dict[str, object]]:
    """Look up titles in one MediaWiki request, following redirects.

    Args:
        titles: Up to ``BATCH_SIZE`` candidate titles.
        session: HTTP session that sends the project User-Agent.

    Returns:
        A map from each requested title to ``status``, ``title``, ``page_id`` and ``length``.
        ``status`` is ``ok``, ``missing`` or ``disambiguation``.

    Raises:
        requests.RequestException: If the request fails.
    """
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "titles": "|".join(titles),
        "redirects": "1",
        "prop": "info|pageprops",
        "ppprop": "disambiguation",
    }
    response = session.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    query = response.json().get("query", {})
    renamed: dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for item in query.get(key, []):
            renamed[item["from"]] = item["to"]
    pages = {page["title"]: page for page in query.get("pages", [])}

    result: dict[str, dict[str, object]] = {}
    for title in titles:
        final = title
        for _ in range(5):
            if final not in renamed:
                break
            final = renamed[final]
        page = pages.get(final)
        if page is None or page.get("missing") or page.get("invalid"):
            result[title] = {"status": "missing", "title": final, "page_id": 0, "length": 0}
        elif "disambiguation" in page.get("pageprops", {}) or page.get("ns") != 0:
            result[title] = {"status": "disambiguation", "title": final, "page_id": 0, "length": 0}
        else:
            result[title] = {
                "status": "ok",
                "title": page["title"],
                "page_id": page["pageid"],
                "length": page.get("length", 0),
            }
    return result


def select(
    candidates: list[tuple[str, str]], info: dict[str, dict[str, object]]
) -> tuple[dict[str, list[str]], list[str]]:
    """Choose the first verified, unique, long-enough titles for every topic.

    Args:
        candidates: Candidate rows in priority order.
        info: Lookup results keyed by candidate title.

    Returns:
        The chosen titles per topic, and a list of human-readable rejection messages.
    """
    chosen: dict[str, list[str]] = defaultdict(list)
    seen_ids: set[int] = set()
    rejected: list[str] = []
    for topic, title in candidates:
        found = info[title]
        reason = ""
        if found["status"] != "ok":
            reason = str(found["status"])
        elif int(found["length"]) < MIN_LENGTH_BYTES:  # type: ignore[arg-type]
            reason = f"too short ({found['length']} bytes)"
        elif int(found["page_id"]) in seen_ids:  # type: ignore[arg-type]
            reason = "duplicate of an earlier candidate"
        elif len(chosen[topic]) >= TARGETS[topic]:
            reason = "not needed (topic already full)"
        if reason:
            rejected.append(f"{topic}: {title} -> {reason}")
            continue
        seen_ids.add(int(found["page_id"]))  # type: ignore[arg-type]
        chosen[topic].append(str(found["title"]))
    return dict(chosen), rejected


def write_seed_file(chosen: dict[str, list[str]], path: Path) -> None:
    """Write the final seed list atomically.

    Args:
        chosen: Selected titles per topic.
        path: Destination CSV file.
    """
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["topic", "title"])
        for topic in TARGETS:
            for title in chosen.get(topic, []):
                writer.writerow([topic, title])
    os.replace(temporary, path)


def main() -> int:
    """Verify all candidates, print a report and write the seed file if every target is met.

    Returns:
        0 if every topic reached its target, otherwise 1 (nothing is written).
    """
    candidates = read_candidates(CANDIDATES)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    titles = [title for _, title in candidates]
    info: dict[str, dict[str, object]] = {}
    for start in range(0, len(titles), BATCH_SIZE):
        info.update(lookup(titles[start : start + BATCH_SIZE], session))
        time.sleep(0.5)
    chosen, rejected = select(candidates, info)
    print(f"Candidates checked: {len(candidates)}")
    for line in rejected:
        print("  rejected:", line)
    short = False
    for topic, target in TARGETS.items():
        count = len(chosen.get(topic, []))
        print(f"{topic}: {count}/{target}")
        short = short or count < target
    if short:
        print("Not every topic reached its target. Add candidates and run again.")
        return 1
    write_seed_file(chosen, OUTPUT)
    print(f"Wrote {sum(map(len, chosen.values()))} titles to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
