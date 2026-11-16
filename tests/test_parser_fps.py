from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.models import Fps, FpsMode
from aiocontrome.parsers import parse_fps

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture
def blocks() -> Mapping[int, Fps]:
    return parse_fps(load_fixture("fps.json"), BERLIN)


def test_all_blocks(blocks: Mapping[int, Fps]) -> None:
    assert sorted(blocks) == [57, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72]
    modes = [b.mode for b in blocks.values()]
    assert modes.count(FpsMode.OUTPUT) == 3
    assert modes.count(FpsMode.OFFSET) == 8


def test_output_block(blocks: Mapping[int, Fps]) -> None:
    block = blocks[64]
    assert block.name == "WP überheizen B WW bereit"
    assert block.mode is FpsMode.OUTPUT
    assert block.value == 0.0
    assert block.last_value == 0.0
    assert block.formula.startswith("(M1 >= M2 - 1)")
    assert block.evaluated["M1"] == 42.6
    assert block.evaluated["override_mode"] == "auto"
    assert block.inputs["modules"]["m1"].startswith("ISG_TEMPERATURE_DHW_ACTUAL_522")
    assert block.inputs["outs"] == {}
    assert block.sliders == {}
    assert block.description.startswith("Aktiv, wenn das Warmwasser")
    assert block.last_evaluated_at == datetime(2026, 11, 13, 10, 27, 6, 260773, tzinfo=UTC)


def test_override(blocks: Mapping[int, Fps]) -> None:
    override = blocks[64].override
    assert override.enabled is False
    assert override.mode == "auto"
    assert override.until is None
    assert (override.on_value, override.off_value) == (1.0, 0.0)


def test_slider(blocks: Mapping[int, Fps]) -> None:
    block = blocks[65]
    assert block.value == 1.0
    slider = block.sliders["v1"]
    assert (slider.value, slider.min, slider.max) == (6.0, 2.0, 12.0)
    assert slider.text.startswith("Mindest-PV-Prognose")
    assert set(block.sliders) == {"v1"}


def test_offset_block(blocks: Mapping[int, Fps]) -> None:
    block = blocks[66]
    assert block.mode is FpsMode.OFFSET
    assert "raum_23_soll" in block.evaluated
    assert block.inputs["outs"]["a1"] == "FPS WP überheizen"


def test_unknown_mode_is_skipped_and_description_fallback() -> None:
    data = {
        "1": {"mode": "neu", "value": 0},
        "2": {"mode": "offset", "value": "1.5", "explanation_text": "fallback", "evaluated": None},
    }
    blocks = parse_fps(data, BERLIN)
    assert list(blocks) == [2]
    assert blocks[2].value == 1.5
    assert blocks[2].description == "fallback"
    assert blocks[2].evaluated == {}
    assert blocks[2].last_evaluated_at is None


@pytest.mark.parametrize(
    "data", [[], {"x": {"mode": "output", "value": 0}}, {"1": {"mode": "output"}}, {"1": None}]
)
def test_invalid_shapes(data: object) -> None:
    with pytest.raises(ContromeResponseError, match="fps/"):
        parse_fps(data, BERLIN)
