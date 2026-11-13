"""Unit tests for the chunk-size experiment helpers."""

import pytest

from wikirag.errors import ValidationError
from wikirag.experiments.chunk_size import parse_settings


def test_parse_settings_returns_pairs_in_order() -> None:
    assert parse_settings(["500:75", "1000:150"]) == [(500, 75), (1000, 150)]


@pytest.mark.parametrize(
    "values",
    [[], ["1000"], ["a:b"], ["100:100"], ["100:200"], ["0:0"], ["100:-1"], ["500:75", "500:75"]],
)
def test_parse_settings_rejects_invalid_input(values: list[str]) -> None:
    with pytest.raises(ValidationError):
        parse_settings(values)
