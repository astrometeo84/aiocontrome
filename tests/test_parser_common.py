from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeApiDisabledError, ContromeResponseError
from aiocontrome.models import Offset
from aiocontrome.parsers._common import (
    check_api_error,
    expect_dict,
    expect_list,
    parse_iso,
    parse_offsets,
    req_float,
    req_int,
    to_float,
    to_int,
    to_str,
    wrap_shape_errors,
)

BERLIN = ZoneInfo("Europe/Berlin")


def test_api_disabled_fixture_raises() -> None:
    data = load_fixture("apiv1_disabled.json")
    with pytest.raises(ContromeApiDisabledError):
        check_api_error(data)
    with pytest.raises(ContromeApiDisabledError):
        expect_dict(data, "x/")


def test_other_error_object_raises_response_error() -> None:
    with pytest.raises(ContromeResponseError, match="'boom'"):
        expect_list({"error": "boom"}, "x/")


def test_expect_shapes() -> None:
    assert expect_list([], "x/") == []
    assert expect_dict({}, "x/") == {}
    with pytest.raises(ContromeResponseError, match="expected a list"):
        expect_list({}, "x/")
    with pytest.raises(ContromeResponseError, match="expected an object"):
        expect_dict([], "x/")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (21, 21.0),
        (18.823529411764707, 18.823529411764707),
        ("6", 6.0),
        (" 2,5 ", 2.5),
        ("kein Sensor vorhanden", None),
        (None, None),
        (True, None),
        ({}, None),
    ],
)
def test_to_float(raw: object, expected: float | None) -> None:
    assert to_float(raw) == expected


def test_to_int_and_required_variants() -> None:
    assert to_int(" 2") == 2
    assert to_int(3.0) == 3
    assert to_int(1.5) is None
    assert req_int("7", "x") == 7
    assert req_float(1, "x") == 1.0
    with pytest.raises(ValueError, match="x is not an integer"):
        req_int(None, "x")
    with pytest.raises(ValueError, match="x is not a number"):
        req_float("abc", "x")


def test_to_str() -> None:
    assert to_str(None) is None
    assert to_str("") is None
    assert to_str("Abends") == "Abends"
    assert to_str(14) == "14"


def test_parse_iso() -> None:
    aware = parse_iso("2026-11-13T18:30:00.684+01:00", BERLIN)
    assert aware is not None and aware.utcoffset() is not None
    assert aware.astimezone(UTC) == datetime(2026, 11, 13, 17, 30, 0, 684000, tzinfo=UTC)
    # Naive ISO values (room_details timer) are local time.
    assert parse_iso("2026-01-02T09:00", BERLIN) == datetime(2026, 1, 2, 9, 0, tzinfo=BERLIN)
    assert parse_iso(None, BERLIN) is None
    assert parse_iso("", BERLIN) is None
    assert parse_iso("tomorrow", BERLIN) is None


def test_parse_offsets_skips_empty_sources() -> None:
    offsets = parse_offsets(
        {"Wetter": {"raum": -0.2, "haus": 0.0}, "api": {}, "x": None, "y": {"raum": 1}}
    )
    assert dict(offsets) == {"Wetter": Offset(-0.2, 0.0), "y": Offset(1.0, 0.0)}
    assert parse_offsets(None) == {}


@pytest.mark.parametrize(
    "api", [{"haus": 0.0}, {"raum": 0.0, "haus": 0.0}], ids=["house-only", "room-and-house"]
)
def test_parse_offsets_api_shapes_after_set_offset(api: dict[str, float]) -> None:
    # Seen live after set-houseoffset / set-roomoffset with 0 K (not recorded as fixture).
    assert dict(parse_offsets({"api": api})) == {"api": Offset(0.0, 0.0)}


def test_wrap_shape_errors() -> None:
    @wrap_shape_errors("demo/")
    def parse(data: dict[str, int]) -> int:
        return data["missing"]

    with pytest.raises(ContromeResponseError, match=r"Unexpected demo/ response: KeyError"):
        parse({})

    @wrap_shape_errors("demo/")
    def disabled() -> None:
        check_api_error({"error": "api_disabled"})

    with pytest.raises(ContromeApiDisabledError):
        disabled()
