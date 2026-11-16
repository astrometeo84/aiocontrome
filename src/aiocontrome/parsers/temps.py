"""Parser for ``temps/``: floors, rooms and their sensors."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from ..models import Floor, House, Room, Sensor
from ..sensors import detect_connection, parse_local_time, parse_temps_time, split_sensor_value
from ._common import (
    LOCAL_MINUTE_FORMAT,
    expect_list,
    parse_offsets,
    req_float,
    req_int,
    to_float,
    to_str,
    wrap_shape_errors,
)


@wrap_shape_errors("temps/")
def parse_temps(data: Any, *, house_id: int, tz: tzinfo) -> House:
    """Parse a ``temps/`` response into a ``House``.

    The response does not contain the house ID; pass the one used in the request.
    """
    floors = expect_list(data, "temps/")
    house_name = next((to_str(f.get("hausname")) for f in floors if f.get("hausname")), None)
    return House(
        id=house_id,
        name=house_name or "",
        floors=tuple(_parse_floor(floor, tz) for floor in floors),
    )


def _parse_floor(floor: Mapping[str, Any], tz: tzinfo) -> Floor:
    floor_id = req_int(floor["id"], "floor id")
    return Floor(
        id=floor_id,
        name=to_str(floor.get("etagenname")) or "",
        rooms=tuple(_parse_room(room, floor_id, tz) for room in floor.get("raeume") or ()),
    )


def _parse_room(room: Mapping[str, Any], floor_id: int, tz: tzinfo) -> Room:
    raw_humidity = room.get("luftfeuchte")
    humidity = to_float(raw_humidity)
    humidity_status = (
        raw_humidity
        if humidity is None and isinstance(raw_humidity, str) and raw_humidity
        else None
    )
    setpoint = req_float(room["solltemperatur"], "solltemperatur")
    permanent_setpoint = to_float(room.get("perm_solltemperatur"))
    return Room(
        id=req_int(room["id"], "room id"),
        name=to_str(room.get("name")) or "",
        floor_id=floor_id,
        temperature=to_float(room.get("temperatur")),
        setpoint=setpoint,
        permanent_setpoint=setpoint if permanent_setpoint is None else permanent_setpoint,
        humidity=humidity,
        humidity_status=humidity_status,
        total_offset=to_float(room.get("total_offset")) or 0.0,
        offsets=parse_offsets(room.get("offsets")),
        current_scene=to_str(room.get("current_temperaturszene_name")),
        next_scene=to_str(room.get("next_temperaturszene_name")),
        next_temperature=to_float(room.get("next_temperature")),
        # next_due_time_rel is ignored on purpose (unreliable); use the absolute time.
        next_due_time=parse_local_time(room.get("next_due_time"), LOCAL_MINUTE_FORMAT, tz),
        mode_end=parse_local_time(room.get("mode_end_datetime"), LOCAL_MINUTE_FORMAT, tz),
        is_temporary_mode=room.get("is_temporary_mode") is True,
        operating_mode=to_str(room.get("betriebsart")) or "",
        allowed_modes=tuple(str(mode) for mode in room.get("allowed_modes") or ()),
        sensors=tuple(_parse_sensor(sensor, tz) for sensor in room.get("sensoren") or ()),
    )


def _parse_sensor(sensor: Mapping[str, Any], tz: tzinfo) -> Sensor:
    sensor_id = str(sensor["name"]).strip()
    value, readings = split_sensor_value(sensor.get("wert"))
    return Sensor(
        id=sensor_id,
        description=to_str(sensor.get("beschreibung")) or "",
        value=value,
        is_room_sensor=sensor.get("raumtemperatursensor") is True,
        last_transmission=parse_temps_time(sensor.get("letzte_uebertragung"), tz),
        connection=detect_connection(sensor_id),
        readings=readings,
    )
