from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.models import House, Offset, Room, SensorConnection
from aiocontrome.parsers import parse_temps

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture
def house(temps: Any) -> House:
    return parse_temps(temps, house_id=1, tz=BERLIN)


def _room(house: House, room_id: int) -> Room:
    return next(r for r in house.rooms if r.id == room_id)


def test_structure(house: House) -> None:
    assert house.id == 1
    assert house.name == ""
    assert [(f.id, f.name) for f in house.floors] == [
        (1, "Dachgeschoss"),
        (5, "1. OG"),
        (6, "EG"),
        (8, "Keller"),
    ]
    assert len(house.rooms) == 11
    assert {r.floor_id for r in house.floors[2].rooms} == {6}


def test_normal_room(house: House) -> None:
    room = _room(house, 1)
    assert room.name == "Büro"
    assert room.temperature == 21.81
    assert room.setpoint == 21.0
    assert room.permanent_setpoint == 21.0
    assert room.humidity == 44.58
    assert room.humidity_status is None
    assert room.total_offset == pytest.approx(-0.1459)
    assert room.current_scene == "Anwesenheit 2"
    assert room.next_scene == "Abends"
    assert room.next_temperature == 19.7
    assert room.next_due_time == datetime(2026, 11, 13, 18, 30, tzinfo=BERLIN)
    assert room.mode_end is None  # "" in the response
    assert room.is_temporary_mode is False
    assert room.operating_mode == "Heating"
    assert room.allowed_modes == ("0", "1", "2", "3")


def test_offsets_vary_and_empty_api_is_dropped(house: House) -> None:
    room = _room(house, 1)
    assert room.offsets["Wetter"] == Offset(-0.2, 0.0)
    assert "api" not in room.offsets
    assert room.offsets["luftfeuchte"].room == pytest.approx(0.0541)


def test_humidity_strings(house: House) -> None:
    no_sensor = _room(house, 23)
    assert no_sensor.humidity is None
    assert no_sensor.humidity_status == "kein Sensor vorhanden"
    no_value = _room(house, 24)
    assert no_value.humidity is None
    assert no_value.humidity_status == "kein aktueller Wert vorhanden"


def test_temperature_null_and_long_floats(house: House) -> None:
    assert _room(house, 24).temperature is None
    assert _room(house, 23).temperature == pytest.approx(18.823529411764707)


def test_sensors_and_room_sensor(house: House) -> None:
    office = _room(house, 1)
    assert [s.id for s in office.sensors] == [
        "28_00_00_00_00_00_02_00",
        "28_00_00_00_00_00_03_00",
        "02:00:00:00:00:01",
    ]
    return_sensor = office.sensors[0]
    assert return_sensor.description == "büro"
    assert return_sensor.value == 25.69
    assert return_sensor.is_room_sensor is False
    assert return_sensor.connection is SensorConnection.ONEWIRE_TEMPERATURE
    assert return_sensor.last_transmission == datetime(2026, 11, 13, 11, 24, tzinfo=BERLIN)
    assert office.room_sensor is not None
    assert office.room_sensor.id == "02:00:00:00:00:01"
    assert office.room_sensor.connection is SensorConnection.RADIO_ROOM_CONTROLLER


def test_radio_multi_sensor_dict(house: House) -> None:
    sensor = _room(house, 23).room_sensor
    assert sensor is not None
    assert sensor.connection is SensorConnection.RADIO_SENSOR
    assert sensor.value == pytest.approx(18.823529411764707)
    assert dict(sensor.readings) == {"Temperatur": pytest.approx(18.823529411764707)}


def test_radio_sensor_without_current_value(house: House) -> None:
    sensor = _room(house, 24).room_sensor
    assert sensor is not None
    assert sensor.value is None
    assert sensor.readings == {}
    assert sensor.last_transmission is None


def test_system_room(house: House) -> None:
    room = _room(house, 26)
    assert room.name == "hk_verteiler"
    assert room.room_sensor is None
    assert room.temperature is None
    assert room.current_scene is None
    assert room.next_due_time is None
    connections = [s.connection for s in room.sensors]
    assert connections.count(SensorConnection.ONEWIRE_TEMPERATURE) == 3
    assert SensorConnection.VIRTUAL in connections


def test_controlled_rooms(house: House) -> None:
    uncontrolled = [r.id for r in house.rooms if not r.is_controlled]
    assert uncontrolled == [26]
    # Radio sensor without outputs and without current value still counts as controlled.
    assert _room(house, 24).is_controlled


@pytest.mark.parametrize("room_id", [1, 14, 15, 16, 17, 18, 19, 20, 23])
def test_return_sensors_match_rltemps(house: House, room_id: int) -> None:
    expected = [s["name"] for s in load_fixture(f"rltemps_{room_id}.json")]
    assert [s.id for s in _room(house, room_id).return_sensors] == expected


def test_return_sensors_exclude_humidity_and_room_sensor(house: House) -> None:
    room = _room(house, 16)
    assert all(not s.is_room_sensor for s in room.return_sensors)
    assert all(s.connection is not SensorConnection.ONEWIRE_HUMIDITY for s in room.return_sensors)
    assert _room(house, 24).return_sensors == ()
    assert _room(house, 26).return_sensors == ()


def test_system_sensors(house: House) -> None:
    descriptions = [s.description for s in house.system_sensors]
    assert descriptions == [
        "og_hkv_vl",
        "dg_hkv_vl",
        "eg_hkv_vl",
        "ISG_TEMPERATURE_DHW_ACTUAL_522",
    ]
    assert _room(house, 1).system_sensors == ()


def test_humidity_sensor(house: House) -> None:
    kinds = {s.connection for s in _room(house, 16).sensors}
    assert SensorConnection.ONEWIRE_HUMIDITY in kinds


def test_house_name_and_missing_optional_fields() -> None:
    data = [
        {
            "hausname": "Haus A",
            "etagenname": "EG",
            "id": 6,
            "raeume": [{"id": 15, "solltemperatur": 20, "sensoren": [{"name": "x"}]}],
        },
        {"id": 7},
    ]
    house = parse_temps(data, house_id=2, tz=BERLIN)
    assert house.name == "Haus A"
    room = house.rooms[0]
    assert room.permanent_setpoint == 20.0
    assert room.humidity is None
    assert room.humidity_status is None
    assert room.sensors[0].connection is SensorConnection.UNKNOWN
    assert house.floors[1].rooms == ()


@pytest.mark.parametrize(
    "data",
    [
        {},
        [{"etagenname": "no id"}],
        [{"id": 1, "raeume": [{"id": 2}]}],  # missing solltemperatur
        [{"id": 1, "raeume": [{"id": 2, "solltemperatur": 20, "sensoren": [{}]}]}],
    ],
)
def test_invalid_shapes(data: object) -> None:
    with pytest.raises(ContromeResponseError, match="temps/"):
        parse_temps(data, house_id=1, tz=BERLIN)


def test_temporary_mode() -> None:
    # Live test: set-ziel with the unchanged setpoint for 30 min in room 23.
    house = parse_temps(load_fixture("temps_temporary_mode.json"), house_id=1, tz=BERLIN)
    room = _room(house, 23)
    assert room.is_temporary_mode is True
    assert room.mode_end == datetime(2026, 11, 15, 14, 50, tzinfo=BERLIN)
    assert room.setpoint == 19.0
    assert room.current_scene == "Anwesenheit 1"  # temps still names the scene
    others = [r for r in house.rooms if r.id != 23]
    assert not any(r.is_temporary_mode or r.mode_end for r in others)
