"""Parser for ``room_details/`` (undocumented, Basic Auth)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any

from ..models import ActiveMode, RoomDetails, Scene, SceneControl, SmartTiming, Timer
from ..sensors import parse_local_time
from ._common import (
    LOCAL_MINUTE_FORMAT,
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


@wrap_shape_errors("room_details/")
def parse_room_details(data: Any, tz: tzinfo) -> tuple[RoomDetails, ...]:
    """Parse a ``room_details/`` response (with or without ``skip_loops``).

    ``heatingLoops``, ``sensors`` and ``unassignedReturnSensors`` are always empty and ignored;
    return sensors come from ``temps/``.
    """
    rooms: list[RoomDetails] = []
    for floor in expect_list(data, "room_details/"):
        floor_key = str(floor["floorId"])
        rooms.extend(_parse_room(room, floor_key, tz) for room in floor.get("rooms") or ())
    return tuple(rooms)


def _parse_room(room: Mapping[str, Any], floor_key: str, tz: tzinfo) -> RoomDetails:
    setpoint = req_float(room["setpoint"], "setpoint")
    permanent_setpoint = to_float(room.get("permanentSetpoint"))
    return RoomDetails(
        id=req_int(room["id"], "room id"),
        room_key=to_str(room.get("roomId")) or "",
        floor_key=floor_key,
        name=to_str(room.get("roomName")) or "",
        icon=to_str(room.get("roomIcon")),
        current_temperature=to_float(room.get("currentTemperature")),
        current_humidity=to_float(room.get("currentHumidity")),
        setpoint=setpoint,
        permanent_setpoint=setpoint if permanent_setpoint is None else permanent_setpoint,
        target_temperature=to_float(room.get("targetTemperature")),
        total_offset=to_float(room.get("totalOffset")) or 0.0,
        temperature_state=to_str(room.get("temperatureState")) or "",
        operating_mode=to_str(room.get("operatingMode")) or "",
        dominant_offset_source=to_str(room.get("dominantOffsetSource")),
        offsets=parse_offsets(room.get("offsets")),
        is_temporary_mode=room.get("isTemporaryMode") is True,
        gateway_offline_minutes=to_int(room.get("gatewayOfflineMinutes")),
        floorcore_mode=to_str(room.get("floorcoreMode")),
        floorcore_state=to_str(room.get("floorcoreZustand")),
        active_mode=_parse_active_mode(room.get("activeMode")),
        scenes=tuple(_parse_scene(scene) for scene in room.get("scenes") or ()),
        scene_control=_parse_scene_control(room.get("sceneControl"), tz),
        timer=_parse_timer(room.get("timer"), tz),
    )


def _parse_active_mode(raw: Any) -> ActiveMode | None:
    if not isinstance(raw, Mapping):
        return None
    return ActiveMode(
        mode_id=req_int(raw["activated_mode_id"], "activated_mode_id"),
        text=to_str(raw.get("activated_mode_text")) or "",
        setpoint=req_float(raw["soll"], "soll"),
        module=to_str(raw.get("mod")) or "",
        priority=to_int(raw.get("priority")) or 0,
        use_offsets=raw.get("use_offsets") is True,
    )


def _parse_scene(raw: Mapping[str, Any]) -> Scene:
    return Scene(
        id=req_int(raw["id"], "scene id"),
        name=to_str(raw.get("name")) or "",
        temperature=req_float(raw["temperature"], "scene temperature"),
        is_active=raw.get("isActive") is True,
    )


def _parse_scene_control(raw: Any, tz: tzinfo) -> SceneControl | None:
    if not isinstance(raw, Mapping):
        return None
    return SceneControl(
        current_scene=to_str(raw.get("currentSceneName")),
        next_scene=to_str(raw.get("nextSceneName")),
        next_temperature=to_float(raw.get("nextTemperature")),
        # nextDueTimeRelative is ignored on purpose: it stays constant between polls.
        next_due_time=parse_local_time(raw.get("nextDueTime"), LOCAL_MINUTE_FORMAT, tz),
        own_schedule=raw.get("ownSchedule") is True,
        smart_timing=_parse_smart_timing(raw.get("smartTiming"), tz),
        mode_end=parse_local_time(raw.get("modeEndDatetime"), LOCAL_MINUTE_FORMAT, tz),
        after_timer_scene=to_str(raw.get("afterTimerSceneName")),
        after_timer_temperature=to_float(raw.get("afterTimerTemperature")),
    )


def _parse_smart_timing(raw: Any, tz: tzinfo) -> SmartTiming | None:
    if not isinstance(raw, Mapping):
        return None
    time = parse_local_time(raw.get("zeit"), LOCAL_MINUTE_FORMAT, tz)
    temperature = to_float(raw.get("temperatur"))
    if time is None or temperature is None:
        return None
    return SmartTiming(
        time=time,
        text=to_str(raw.get("text")) or "",
        state=to_str(raw.get("zustand")) or "",
        temperature=temperature,
    )


def _parse_timer(raw: Any, tz: tzinfo) -> Timer | None:
    if not isinstance(raw, Mapping):
        return None
    return Timer(
        running=raw.get("running") is True,
        active=raw.get("active") is True,
        planned=raw.get("planned") is True,
        offset=to_float(raw.get("offset")) or 0.0,
        current_offset=to_float(raw.get("currentOffset")) or 0.0,
        start=parse_iso(raw.get("start"), tz),
        end=parse_iso(raw.get("end"), tz),
        duration_minutes=to_int(raw.get("durationMinutes")),
    )
