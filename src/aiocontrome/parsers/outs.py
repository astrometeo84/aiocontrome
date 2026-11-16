"""Parser for ``outs/``: gateway outputs per room."""

from __future__ import annotations

import logging
from typing import Any

from ..models import Output
from ..outputs import OutputTypeDetector
from ._common import expect_list, req_int, to_float, to_int, wrap_shape_errors

_LOGGER = logging.getLogger(__name__)


@wrap_shape_errors("outs/")
def parse_outs(data: Any, detector: OutputTypeDetector | None = None) -> tuple[Output, ...]:
    """Parse an ``outs/`` response.

    Keys may carry a leading space (``" 2"``) and are stripped. All values are fed into
    ``detector`` before types are assigned. Pass a long-lived detector to keep evidence across
    polls; without one, detection only uses this response.
    """
    floors = expect_list(data, "outs/")
    detector = detector or OutputTypeDetector()
    raw: list[tuple[int, int, int, float]] = []
    for floor in floors:
        floor_id = req_int(floor["id"], "floor id")
        for room in floor.get("raeume") or ():
            room_id = req_int(room["id"], "room id")
            for key, value in (room.get("ausgang") or {}).items():
                number, number_value = to_int(str(key).strip()), to_float(value)
                if number is None or number_value is None:
                    _LOGGER.debug(
                        "Skipping output %r=%r of room %s: not numeric", key, value, room_id
                    )
                    continue
                raw.append((floor_id, room_id, number, number_value))
    for floor_id, _, _, value in raw:
        detector.observe(floor_id, value)
    return tuple(
        Output(floor_id, room_id, number, value, detector.type_for(floor_id))
        for floor_id, room_id, number, value in raw
    )
