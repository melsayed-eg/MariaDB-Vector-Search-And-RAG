"""Unit tests for the chunk-size experiment workflow, using mocks."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from wikirag.errors import ValidationError, WikiRagError
from wikirag.experiments import chunk_size
from wikirag.models import IngestReport


def _metrics() -> SimpleNamespace:
    """Build fake mode metrics."""
    return SimpleNamespace(
        n_queries=2,
        recall_at_k={1: 0.5},
        precision_at_k={1: 0.5},
        mrr=0.5,
        latency_ms_p50=1.0,
        latency_ms_p95=2.0,
    )


class _Conn:
    """Fake database connection."""

    def close(self) -> None:
        """Close the fake connection."""


class _Repo:
    """Fake repository with a fixed chunk count."""

    chunks = 7

    def __init__(self, config: Any) -> None:
        """Store the config."""
        self.config = config

    def __enter__(self) -> "_Repo":
        """Enter the context."""
        return self

    def __exit__(self, *args: object) -> None:
        """Leave the context."""

    def count_chunks(self) -> int:
        """Return the fake chunk count."""
        return self.chunks


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the database, ingestion and evaluation calls with fakes.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        A dictionary the fakes record their calls in.
    """
    calls: dict[str, Any] = {"eval": [], "reports": []}
    report = SimpleNamespace(modes={"semantic": _metrics(), "hybrid": _metrics()})

    def fake_eval(queries: Any, retriever: Any, **kwargs: Any) -> SimpleNamespace:
        """Record an evaluation call."""
        calls["eval"].append(kwargs)
        return report

    monkeypatch.setattr(chunk_size, "load_queries", lambda *a, **k: [object()])
    monkeypatch.setattr(chunk_size, "get_connection", lambda config: _Conn())
    monkeypatch.setattr(chunk_size, "init_schema", lambda *a, **k: None)
    monkeypatch.setattr(chunk_size, "WikiRepository", _Repo)
    monkeypatch.setattr(chunk_size, "Retriever", lambda repo, embedder: object())
    monkeypatch.setattr(chunk_size, "run_evaluation", fake_eval)
    monkeypatch.setattr(
        chunk_size, "write_report", lambda rep, j, m: calls["reports"].append((j, m))
    )
    calls["ingest"] = IngestReport(inserted=2, updated=0, skipped=0, failed=())
    monkeypatch.setattr(chunk_size, "ingest_snapshot", lambda *a, **k: calls["ingest"])
    return calls


def _run(tmp_path: Path) -> dict[str, object]:
    """Call run_setting with dummy arguments."""
    return chunk_size.run_setting(
        config=object(),  # type: ignore[arg-type]
        embedder=SimpleNamespace(model_name="m"),  # type: ignore[arg-type]
        snapshot_path=tmp_path / "s.jsonl",
        queries_path=tmp_path / "q.jsonl",
        max_chars=500,
        overlap_chars=75,
        out_dir=tmp_path,
        limit=None,
        repeats=1,
    )


def test_parse_settings_returns_pairs_in_order() -> None:
    """Valid settings are parsed in order."""
    assert chunk_size.parse_settings(["500:75", "1000:150"]) == [(500, 75), (1000, 150)]


@pytest.mark.parametrize(
    "values",
    [[], ["1000"], ["a:b"], ["100:100"], ["100:200"], ["0:0"], ["100:-1"], ["500:75", "500:75"]],
)
def test_parse_settings_rejects_invalid_input(values: list[str]) -> None:
    """Malformed or duplicate settings raise ValidationError."""
    with pytest.raises(ValidationError):
        chunk_size.parse_settings(values)


def test_run_setting_builds_result_and_reports(patched: dict[str, Any], tmp_path: Path) -> None:
    """A successful run returns metrics for all modes and writes two reports."""
    row = _run(tmp_path)
    assert row["chunks"] == 7
    assert row["articles_failed"] == 0
    assert set(row["modes"]) == {"semantic", "hybrid", "semantic_all_queries"}  # type: ignore[arg-type]
    assert len(patched["reports"]) == 2


def test_run_setting_requires_compliance_for_hybrid_comparison(
    patched: dict[str, Any], tmp_path: Path
) -> None:
    """The semantic/hybrid comparison is run with require_compliance=True."""
    _run(tmp_path)
    comparison = [c for c in patched["eval"] if "hybrid" in c["modes"]]
    assert comparison
    assert all(c.get("require_compliance") is True for c in comparison)


def test_failed_ingestion_stops_before_evaluation(patched: dict[str, Any], tmp_path: Path) -> None:
    """Failed articles raise an error and nothing is evaluated or written."""
    patched["ingest"] = IngestReport(inserted=1, updated=0, skipped=0, failed=(("A", "boom"),))
    with pytest.raises(WikiRagError, match="Ingestion failed"):
        _run(tmp_path)
    assert patched["eval"] == []
    assert patched["reports"] == []


def test_no_stored_chunks_stops_the_run(
    patched: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty corpus raises an error instead of publishing results."""
    monkeypatch.setattr(_Repo, "chunks", 0)
    with pytest.raises(WikiRagError, match="No chunks"):
        _run(tmp_path)
    monkeypatch.setattr(_Repo, "chunks", 7)


@pytest.mark.parametrize(
    ("test_name", "main_name"),
    [("wikirag", "wikirag"), ("wikirag_prod", "wikirag"), ("wikirag_test", "wikirag_test")],
)
def test_unsafe_database_is_rejected(
    monkeypatch: pytest.MonkeyPatch, test_name: str, main_name: str
) -> None:
    """The experiment refuses databases that are not a separate _test database."""
    settings = SimpleNamespace(db_name_test=test_name, db=SimpleNamespace(database=main_name))
    monkeypatch.setattr(chunk_size, "load_settings", lambda: settings)
    with pytest.raises(ValidationError):
        chunk_size.experiment_database_config()


def test_comparison_writes_summary_with_environment(
    patched: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The summary lists every setting, checksums and the environment."""
    snapshot, queries = tmp_path / "s.jsonl", tmp_path / "q.jsonl"
    snapshot.write_text("a", encoding="utf-8")
    queries.write_text("b", encoding="utf-8")
    monkeypatch.setattr(chunk_size, "collect_run_metadata", lambda config: {"cpu": "x"})
    summary = chunk_size.run_chunk_size_comparison(
        [(500, 75), (1000, 150)],
        snapshot_path=snapshot,
        queries_path=queries,
        out_dir=tmp_path / "out",
        repeats=1,
        embedder=SimpleNamespace(model_name="m"),  # type: ignore[arg-type]
        config=object(),  # type: ignore[arg-type]
    )
    assert len(summary["results"]) == 2  # type: ignore[arg-type]
    assert summary["environment"] == {"cpu": "x"}
    assert (tmp_path / "out" / "summary.json").is_file()


def test_comparison_rejects_empty_settings(tmp_path: Path) -> None:
    """An empty settings list raises ValidationError."""
    with pytest.raises(ValidationError):
        chunk_size.run_chunk_size_comparison(
            [], snapshot_path=tmp_path, queries_path=tmp_path, out_dir=tmp_path
        )
