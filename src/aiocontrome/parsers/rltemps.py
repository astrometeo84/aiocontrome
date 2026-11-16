"""Parser for ``rltemps/<room>/``: return-flow sensors of a room."""

from __future__ import annotations

from datetime import tzinfo
from typing import Any

from ..models import ReturnSensor
from ..sensors import parse_rltemps_time, split_sensor_value
from ._common import expect_list, req_int, to_str, wrap_shape_errors


@wrap_shape_errors("rltemps/")
def parse_rltemps(data: Any, tz: tzinfo) -> tuple[ReturnSensor, ...]:
    """Parse an ``rltemps/<room>/`` response.

    The timestamp format differs from ``temps/`` (``HH:MM:SS dd.mm.yyyy``). The ``ausgang``
    field is always ``null`` and therefore ignored.
    """
    return tuple(
        ReturnSensor(
            id=req_int(sensor["id"], "sensor id"),
            sensor_id=str(sensor["name"]).strip(),
            description=to_str(sensor.get("beschreibung")) or "",
            value=split_sensor_value(sensor.get("wert"))[0],
            last_transmission=parse_rltemps_time(sensor.get("letzte_uebertragung"), tz),
        )
        for sensor in expect_list(data, "rltemps/")
    )
