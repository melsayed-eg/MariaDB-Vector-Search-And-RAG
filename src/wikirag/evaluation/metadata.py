"""Collect reproducibility metadata for retrieval benchmarks."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    """Calculate a file's SHA-256 checksum.

    Args:
        path: File to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_output(*command: str) -> str | None:
    """Read command output without failing on unavailable utilities.

    Args:
        command: Executable and its arguments.

    Returns:
        Stripped stdout, or None when unavailable.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def collect_metadata(
    *,
    connection: Any,
    snapshot_path: Path,
    dataset_path: Path,
    embedding_model: str,
    embedding_dimension: int,
    article_count: int,
    chunk_count: int,
    ks: tuple[int, ...],
    chunk_pool: int,
    repeats: int,
) -> dict[str, Any]:
    """Collect benchmark configuration and execution environment.

    Args:
        connection: Active MariaDB connection.
        snapshot_path: Committed Wikipedia snapshot.
        dataset_path: Evaluation query dataset.
        embedding_model: Actual embedding model identifier.
        embedding_dimension: Embedding vector dimension.
        article_count: Number of stored articles.
        chunk_count: Number of stored chunks.
        ks: Article-level retrieval cutoff values.
        chunk_pool: Number of retrieved chunks per request.
        repeats: Number of measured runs per question.

    Returns:
        JSON-serializable benchmark metadata.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION() AS version")
        database_version = cursor.fetchone()["version"]

        cursor.execute("SHOW VARIABLES LIKE 'mhnsw%'")
        hnsw_variables = {row["Variable_name"]: row["Value"] for row in cursor.fetchall()}

        cursor.execute("SHOW CREATE TABLE chunks")
        table_definition = cursor.fetchone()["Create Table"]

    cpu = platform.processor() or None
    ram_bytes = None

    if sys.platform == "darwin":
        cpu = (
            command_output("sysctl", "-n", "machdep.cpu.brand_string")
            or (command_output("sysctl", "-n", "hw.model"))
            or cpu
        )
        ram = command_output("sysctl", "-n", "hw.memsize")
        ram_bytes = int(ram) if ram and ram.isdigit() else None
    elif sys.platform.startswith("linux"):
        cpu = platform.processor() or command_output("uname", "-m")
        ram_kib = None
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    ram_kib = int(line.split()[1])
                    break
        except OSError:
            pass
        ram_bytes = ram_kib * 1024 if ram_kib is not None else None

    return {
        "benchmark_utc": datetime.now(UTC).isoformat(),
        "git_commit": command_output("git", "rev-parse", "HEAD"),
        "git_worktree_status": command_output("git", "status", "--porcelain"),
        "python_version": sys.version.split()[0],
        "operating_system": platform.platform(),
        "hardware": {
            "machine": platform.machine(),
            "cpu": cpu,
            "ram_bytes": ram_bytes,
        },
        "mariadb_version": database_version,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "snapshot_sha256": file_sha256(snapshot_path),
        "dataset_sha256": file_sha256(dataset_path),
        "corpus_articles": article_count,
        "corpus_chunks": chunk_count,
        "ks": list(ks),
        "chunk_pool": chunk_pool,
        "warmup_runs_per_query": 1,
        "measured_runs_per_query": repeats,
        "hnsw_session_variables": hnsw_variables,
        "chunks_table_definition": table_definition,
        "search_strategies": {
            "semantic": "HNSW-eligible cosine vector search",
            "hybrid": "Exact cosine ranking with relational SQL filters",
        },
        "timing_methodology": (
            "Retriever latency measured with perf_counter; "
            "one warm-up request per query and mode; "
            "P50/P95 computed across per-query means of measured repetitions."
        ),
    }


def write_metadata(metadata: dict[str, Any], path: Path) -> None:
    """Write benchmark metadata as formatted JSON.

    Args:
        metadata: JSON-serializable benchmark information.
        path: Output file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
