"""Unit tests for bounded retry of temporary Wikipedia errors."""

import pytest
import requests

from wikirag.errors import WikiRagError
from wikirag.ingestion import wikipedia


class FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> dict[str, object]:
        return {"ok": True}


class FakeSession:
    def __init__(self, statuses: list[int], headers: dict[str, str] | None = None) -> None:
        self.statuses = statuses
        self.headers = headers
        self.calls = 0

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return FakeResponse(status, self.headers)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(wikipedia.time, "sleep", recorded.append)
    return recorded


def test_retries_temporary_error_then_succeeds(sleeps: list[float]) -> None:
    session = FakeSession([429, 503, 200])
    assert wikipedia._get_json(session, {}, 5.0) == {"ok": True}
    assert session.calls == 3
    assert sleeps == [1.0, 2.0]


def test_retry_after_header_is_respected_and_capped(sleeps: list[float]) -> None:
    session = FakeSession([429, 429, 200], headers={"Retry-After": "999"})
    wikipedia._get_json(session, {}, 5.0)
    assert sleeps == [wikipedia.MAX_RETRY_AFTER_S, wikipedia.MAX_RETRY_AFTER_S]


def test_gives_up_after_maximum_retries(sleeps: list[float]) -> None:
    session = FakeSession([503])
    with pytest.raises(WikiRagError):
        wikipedia._get_json(session, {}, 5.0)
    assert session.calls == wikipedia.MAX_RETRIES + 1
    assert len(sleeps) == wikipedia.MAX_RETRIES


def test_permanent_error_is_not_retried(sleeps: list[float]) -> None:
    session = FakeSession([404])
    with pytest.raises(WikiRagError):
        wikipedia._get_json(session, {}, 5.0)
    assert session.calls == 1
    assert sleeps == []
