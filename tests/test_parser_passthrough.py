"""Tests for the pass-through parser (``vtr/``, ``wetter_pro/``)."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeApiDisabledError, ContromeResponseError
from aiocontrome.parsers import parse_passthrough


@pytest.mark.parametrize("fixture", ["vtr_empty.json", "wetter_pro_empty.json"])
def test_not_configured_is_empty(fixture: str) -> None:
    assert parse_passthrough(load_fixture(fixture), "vtr/") == {}


def test_payload_is_deep_frozen() -> None:
    data: dict[str, Any] = {"mischer": [{"id": 1, "werte": {"vl": 35.5}}], "aktiv": True}
    result = parse_passthrough(data, "vtr/")
    assert result["mischer"] == ({"id": 1, "werte": {"vl": 35.5}},)
    assert result["aktiv"] is True
    with pytest.raises(TypeError):
        result["mischer"][0]["id"] = 2  # type: ignore[index]
    data["aktiv"] = False  # the result is a copy
    assert result["aktiv"] is True


@pytest.mark.parametrize("data", [[], "x", None])
def test_non_object_raises(data: Any) -> None:
    with pytest.raises(ContromeResponseError, match="wetter_pro/"):
        parse_passthrough(data, "wetter_pro/")


def test_api_disabled() -> None:
    with pytest.raises(ContromeApiDisabledError):
        parse_passthrough(load_fixture("apiv1_disabled.json"), "vtr/")
