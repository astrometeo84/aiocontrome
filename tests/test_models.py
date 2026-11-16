from __future__ import annotations

import dataclasses
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import aiocontrome
from aiocontrome.models import (
    WINDOW_OPEN_OFFSET_SOURCE,
    Floor,
    House,
    Offset,
    Room,
    RoomDetails,
    Sensor,
    SensorConnection,
)

BERLIN = ZoneInfo("Europe/Berlin")


def _sensor(sensor_id: str, *, room_sensor: bool) -> Sensor:
    return Sensor(
        id=sensor_id,
        description="x",
        value=20.0,
        is_room_sensor=room_sensor,
        last_transmission=datetime(2026, 11, 13, 11, 24, tzinfo=BERLIN),
        connection=SensorConnection.ONEWIRE_TEMPERATURE,
    )


def _room(room_id: int, sensors: tuple[Sensor, ...] = ()) -> Room:
    return Room(
        id=room_id,
        name=f"room {room_id}",
        floor_id=1,
        temperature=None,
        setpoint=21.0,
        permanent_setpoint=21.0,
        humidity=None,
        humidity_status="kein Sensor vorhanden",
        total_offset=0.0,
        offsets={},
        current_scene=None,
        next_scene=None,
        next_temperature=None,
        next_due_time=None,
        mode_end=None,
        is_temporary_mode=False,
        operating_mode="Heating",
        allowed_modes=("0", "1"),
        sensors=sensors,
    )


def _details(offsets: dict[str, Offset]) -> RoomDetails:
    return RoomDetails(
        id=23,
        room_key="room-023",
        floor_key="floor-03",
        name="Gästeklo",
        icon=None,
        current_temperature=18.8,
        current_humidity=None,
        setpoint=20.0,
        permanent_setpoint=20.0,
        target_temperature=10.0,
        total_offset=-10.0,
        temperature_state="above_target",
        operating_mode="Heating",
        dominant_offset_source="fenster_offen",
        offsets=offsets,
        is_temporary_mode=False,
        gateway_offline_minutes=None,
        floorcore_mode=None,
        floorcore_state=None,
        active_mode=None,
        scenes=(),
        scene_control=None,
        timer=None,
    )


def test_models_are_frozen() -> None:
    sensor = _sensor("28_00_00_00_00_00_05_00", room_sensor=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        sensor.value = 1.0  # type: ignore[misc]
    assert sensor.readings == {}


def test_room_sensor() -> None:
    room_sensor = _sensor("02:00:00:00:00:01", room_sensor=True)
    room = _room(1, (_sensor("28_00_00_00_00_00_02_00", room_sensor=False), room_sensor))
    assert room.room_sensor is room_sensor
    assert _room(26).room_sensor is None


def test_house_rooms() -> None:
    house = House(1, "", (Floor(1, "DG", (_room(1),)), Floor(5, "1. OG", (_room(14), _room(16)))))
    assert [r.id for r in house.rooms] == [1, 14, 16]


@pytest.mark.parametrize(
    ("offsets", "expected"),
    [
        ({WINDOW_OPEN_OFFSET_SOURCE: Offset(-10.0, 0.0)}, True),
        ({WINDOW_OPEN_OFFSET_SOURCE: Offset(0.0, 0.0)}, False),
        ({"Wetter": Offset(-0.2, 0.0)}, False),
    ],
)
def test_window_open(offsets: dict[str, Offset], expected: bool) -> None:
    assert _details(offsets).window_open is expected


def test_public_api_exports() -> None:
    for name in aiocontrome.__all__:
        assert hasattr(aiocontrome, name), name
