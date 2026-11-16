"""Parser for ``upcomingoffsets/``."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any

from ..models import UpcomingChange, UpcomingOffsets
from ._common import expect_dict, parse_iso, req_int, to_int, to_str, wrap_shape_errors

type _ByModule = Mapping[str, tuple[UpcomingChange, ...]]


@wrap_shape_errors("upcomingoffsets/")
def parse_upcoming_offsets(data: Any, tz: tzinfo) -> UpcomingOffsets:
    """Parse ``upcomingoffsets/``.

    Entries are ``[iso_time, id | null, kind]``; malformed entries are skipped. The
    ``regelungs`` section is not modelled.
    """
    payload = expect_dict(data, "upcomingoffsets/")
    return UpcomingOffsets(
        houses=_parse_section(payload.get("houses"), tz),
        rooms=_parse_section(payload.get("rooms"), tz),
    )


def _parse_section(raw: Any, tz: tzinfo) -> Mapping[int, _ByModule]:
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    return MappingProxyType(
        {req_int(key, "id"): _parse_modules(modules, tz) for key, modules in raw.items()}
    )


def _parse_modules(raw: Any, tz: tzinfo) -> _ByModule:
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    return MappingProxyType(
        {
            str(module): tuple(
                change for entry in entries or () if (change := _parse_entry(entry, tz)) is not None
            )
            for module, entries in raw.items()
        }
    )


def _parse_entry(raw: Any, tz: tzinfo) -> UpcomingChange | None:
    if not isinstance(raw, list | tuple) or len(raw) < 3:
        return None
    time = parse_iso(raw[0], tz)
    if time is None:
        return None
    return UpcomingChange(time=time, target_id=to_int(raw[1]), kind=to_str(raw[2]) or "")
