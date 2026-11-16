from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.parsers import parse_upcoming_offsets

BERLIN = ZoneInfo("Europe/Berlin")


def test_house_heating_program() -> None:
    upcoming = parse_upcoming_offsets(load_fixture("upcomingoffsets.json"), BERLIN)
    program = upcoming.houses[1]["heizprogramm"]
    assert [(c.target_id, c.kind) for c in program] == [
        (15, "mode-change"),
        (14, "mode-change"),
        (None, "ending-list"),
    ]
    first = program[0].time
    assert first.utcoffset() is not None
    assert first.astimezone(UTC) == datetime(2026, 11, 13, 17, 30, 0, 684000, tzinfo=UTC)
    assert set(upcoming.houses[1]) == {"jahreskalender", "timer", "heizprogramm"}


def test_rooms() -> None:
    upcoming = parse_upcoming_offsets(load_fixture("upcomingoffsets.json"), BERLIN)
    assert 1 in upcoming.rooms
    (end,) = upcoming.rooms[1]["timer"]
    assert (end.target_id, end.kind) == (None, "ending-list")


def test_malformed_entries_are_skipped() -> None:
    data = {
        "houses": {"1": {"timer": [["no time", None, "x"], ["2026-11-13T18:30:00+01:00"], 5]}},
        "rooms": {"2": "nope"},
    }
    upcoming = parse_upcoming_offsets(data, BERLIN)
    assert upcoming.houses[1]["timer"] == ()
    assert upcoming.rooms[2] == {}
    assert parse_upcoming_offsets({}, BERLIN).houses == {}


@pytest.mark.parametrize("data", [[], {"houses": {"abc": {}}}])
def test_invalid_shapes(data: object) -> None:
    with pytest.raises(ContromeResponseError, match="upcomingoffsets/"):
        parse_upcoming_offsets(data, BERLIN)
