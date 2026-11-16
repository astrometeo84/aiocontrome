from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conftest import iter_sensors, load_fixture

from aiocontrome.models import SensorConnection
from aiocontrome.sensors import (
    LastSeenTracker,
    detect_connection,
    is_stale,
    parse_rltemps_time,
    parse_temps_time,
    split_sensor_value,
)

BERLIN = ZoneInfo("Europe/Berlin")


def _sensor(data: Any, sensor_id: str) -> dict[str, Any]:
    return next(s for s in iter_sensors(data) if s["name"] == sensor_id)


# --- connection type ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sensor_id", "expected"),
    [
        ("28_00_00_00_00_00_05_00", SensorConnection.ONEWIRE_TEMPERATURE),
        ("26_00_00_00_00_00_0a_00", SensorConnection.ONEWIRE_HUMIDITY),
        ("02:00:00:00:00:01", SensorConnection.RADIO_ROOM_CONTROLLER),
        ("05:00:00:01", SensorConnection.RADIO_SENSOR),
        ("12_00_00_00_00_00_00_0c", SensorConnection.VIRTUAL),
        ("ISG_TEMPERATURE_DHW", SensorConnection.UNKNOWN),
        ("28_00_00", SensorConnection.UNKNOWN),
        ("", SensorConnection.UNKNOWN),
    ],
)
def test_detect_connection(sensor_id: str, expected: SensorConnection) -> None:
    assert detect_connection(sensor_id) is expected


def test_every_fixture_sensor_has_a_known_connection(temps: Any) -> None:
    connections = {detect_connection(s["name"]) for s in iter_sensors(temps)}
    assert SensorConnection.UNKNOWN not in connections
    assert connections == set(SensorConnection) - {SensorConnection.UNKNOWN}


# --- values ---------------------------------------------------------------------------------


def test_numeric_value(temps: Any) -> None:
    value, readings = split_sensor_value(_sensor(temps, "28_00_00_00_00_00_02_00")["wert"])
    assert value == 25.69
    assert readings == {}


def test_multi_sensor_dict_uses_temperature_and_drops_nulls(temps: Any) -> None:
    value, readings = split_sensor_value(_sensor(temps, "05:00:00:01")["wert"])
    assert value == pytest.approx(18.823529411764707)
    assert dict(readings) == {"Temperatur": pytest.approx(18.823529411764707)}


def test_multi_sensor_dict_all_null(temps: Any) -> None:
    value, readings = split_sensor_value(_sensor(temps, "05:00:00:02")["wert"])
    assert value is None
    assert readings == {}


def test_multi_sensor_dict_without_temperature() -> None:
    value, readings = split_sensor_value({"Temperatur": None, "Relative Luftfeuchte": 51})
    assert value is None
    assert dict(readings) == {"Relative Luftfeuchte": 51.0}


@pytest.mark.parametrize("raw", [None, "kein aktueller Wert vorhanden", True, [1]])
def test_non_numeric_values(raw: object) -> None:
    assert split_sensor_value(raw) == (None, {})


# --- timestamps -----------------------------------------------------------------------------


def test_parse_temps_time(temps: Any) -> None:
    raw = _sensor(temps, "05:00:00:01")["letzte_uebertragung"]
    assert parse_temps_time(raw, BERLIN) == datetime(2026, 11, 13, 11, 17, tzinfo=BERLIN)


def test_parse_temps_time_null_means_no_current_value(temps: Any) -> None:
    raw = _sensor(temps, "05:00:00:02")["letzte_uebertragung"]
    assert raw is None
    assert parse_temps_time(raw, BERLIN) is None


def test_parse_rltemps_time() -> None:
    raw = load_fixture("rltemps_23.json")[0]["letzte_uebertragung"]
    parsed = parse_rltemps_time(raw, BERLIN)
    assert parsed == datetime(2026, 11, 13, 10, 49, 33, tzinfo=BERLIN)
    assert parsed is not None and parsed.utcoffset() == timedelta(hours=1)


@pytest.mark.parametrize("raw", ["", "13.11.2026", "10:49:33 13.11.2026"])
def test_parse_temps_time_rejects_other_formats(raw: str) -> None:
    assert parse_temps_time(raw, BERLIN) is None


def test_parse_rltemps_time_rejects_temps_format() -> None:
    assert parse_rltemps_time("13.11.2026 11:24", BERLIN) is None


# --- staleness ------------------------------------------------------------------------------


def test_is_stale() -> None:
    now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    max_age = timedelta(minutes=30)
    assert is_stale(None, now, max_age)
    assert not is_stale(now - timedelta(minutes=30), now, max_age)
    assert is_stale(now - timedelta(minutes=31), now, max_age)


def test_last_seen_tracker_keeps_time_when_null_is_reported() -> None:
    tracker = LastSeenTracker()
    first = datetime(2026, 11, 13, 11, 17, tzinfo=BERLIN)
    assert tracker.get("05:00:00:02") is None
    assert tracker.update("05:00:00:02", None) is None
    assert tracker.update("05:00:00:02", first) == first
    assert tracker.update("05:00:00:02", None) == first
    assert tracker.update("05:00:00:02", first - timedelta(minutes=5)) == first
    later = first + timedelta(minutes=20)
    assert tracker.update("05:00:00:02", later) == later
    assert tracker.get("05:00:00:02") == later
