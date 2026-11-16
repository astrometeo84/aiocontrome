from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from conftest import FIXTURES, load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.parsers import parse_rltemps

BERLIN = ZoneInfo("Europe/Berlin")


def test_parse_rltemps_uses_its_own_time_format() -> None:
    (sensor,) = parse_rltemps(load_fixture("rltemps_23.json"), BERLIN)
    assert sensor.id == 18
    assert sensor.sensor_id == "28_00_00_00_00_00_15_00"
    assert sensor.description == "gaesteklo_rl"
    assert sensor.value == 24.94
    assert sensor.last_transmission == datetime(2026, 11, 13, 10, 49, 33, tzinfo=BERLIN)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("rltemps_*.json")), ids=lambda p: p.name)
def test_all_rltemps_fixtures(path: Path) -> None:
    sensors = parse_rltemps(load_fixture(path.name), BERLIN)
    assert sensors
    assert all(s.last_transmission is not None for s in sensors)
    assert all(s.value is not None for s in sensors)


def test_null_time_and_value() -> None:
    (sensor,) = parse_rltemps(
        [{"id": 1, "name": "x", "wert": None, "letzte_uebertragung": None}], BERLIN
    )
    assert sensor.value is None
    assert sensor.last_transmission is None


@pytest.mark.parametrize("data", [{}, [{"name": "no id"}]])
def test_invalid_shapes(data: object) -> None:
    with pytest.raises(ContromeResponseError, match="rltemps/"):
        parse_rltemps(data, BERLIN)
