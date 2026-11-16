"""Parser for ``fps/``: free programmable control blocks (read-only)."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import tzinfo
from types import MappingProxyType
from typing import Any

from ..models import Fps, FpsMode, FpsOverride, FpsSlider
from ._common import expect_dict, parse_iso, req_float, req_int, to_float, to_str, wrap_shape_errors

_LOGGER = logging.getLogger(__name__)
_SLIDER_VALUE_KEY = re.compile(r"^v\d+$")


@wrap_shape_errors("fps/")
def parse_fps(data: Any, tz: tzinfo) -> Mapping[int, Fps]:
    """Parse ``fps/`` into ``{fps_id: Fps}``. Blocks with an unknown mode are skipped."""
    blocks: dict[int, Fps] = {}
    for key, raw in expect_dict(data, "fps/").items():
        fps_id = req_int(key, "fps id")
        try:
            mode = FpsMode(raw["mode"])
        except ValueError:
            _LOGGER.debug("Skipping FPS %s with unknown mode %r", fps_id, raw["mode"])
            continue
        blocks[fps_id] = _parse_block(fps_id, mode, raw, tz)
    return MappingProxyType(blocks)


def _parse_block(fps_id: int, mode: FpsMode, raw: Mapping[str, Any], tz: tzinfo) -> Fps:
    return Fps(
        id=fps_id,
        name=to_str(raw.get("name")) or "",
        mode=mode,
        value=req_float(raw["value"], "value"),
        last_value=to_float(raw.get("last_value")),
        formula=to_str(raw.get("formula")) or "",
        evaluated=_parse_evaluated(raw.get("evaluated")),
        inputs=_parse_inputs(raw.get("variables_details")),
        sliders=_parse_sliders(raw.get("user_variables")),
        override=FpsOverride(
            enabled=raw.get("override_enabled") is True,
            mode=to_str(raw.get("override_mode")) or "",
            until=parse_iso(raw.get("override_until"), tz),
            on_value=to_float(raw.get("override_on_value")),
            off_value=to_float(raw.get("override_off_value")),
        ),
        last_evaluated_at=parse_iso(raw.get("last_evaluated_at"), tz),
        description=to_str(raw.get("explanation_user_txt"))
        or to_str(raw.get("explanation_text"))
        or "",
    )


def _parse_evaluated(raw: Any) -> Mapping[str, float | str]:
    result: dict[str, float | str] = {}
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if isinstance(value, str):
                result[str(key)] = value
            elif (number := to_float(value)) is not None:
                result[str(key)] = number
    return MappingProxyType(result)


def _parse_inputs(raw: Any) -> Mapping[str, Mapping[str, str]]:
    """``variables_details``: ``{"sensors"|"outs"|"modules": {variable: label}}``."""
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    return MappingProxyType(
        {
            str(group): MappingProxyType({str(k): str(v) for k, v in items.items()})
            for group, items in raw.items()
            if isinstance(items, Mapping)
        }
    )


def _parse_sliders(raw: Any) -> Mapping[str, FpsSlider]:
    """Group flat ``v1``/``v1_min_slider``/``v1_max_slider``/``v1_slider_text`` strings."""
    sliders: dict[str, FpsSlider] = {}
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            if not _SLIDER_VALUE_KEY.match(str(key)) or (number := to_float(value)) is None:
                continue
            sliders[key] = FpsSlider(
                value=number,
                min=to_float(raw.get(f"{key}_min_slider")),
                max=to_float(raw.get(f"{key}_max_slider")),
                text=to_str(raw.get(f"{key}_slider_text")) or "",
            )
    return MappingProxyType(sliders)
