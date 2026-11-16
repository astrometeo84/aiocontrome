from __future__ import annotations

import pytest
from conftest import iter_outputs, load_fixture

from aiocontrome.models import Output, OutputType
from aiocontrome.outputs import OutputTypeDetector


def _outputs(name: str, detector: OutputTypeDetector) -> list[Output]:
    raw = iter_outputs(load_fixture(name))
    for floor_id, _, _, value in raw:
        detector.observe(floor_id, value)
    return [
        Output(floor_id, room_id, int(key.strip()), value, detector.type_for(floor_id))
        for floor_id, room_id, key, value in raw
    ]


def test_pro_gateway_detected_from_value_above_one() -> None:
    detector = OutputTypeDetector()
    outputs = _outputs("outs_pro_a.json", detector)
    # Gästezimmer (floor 5) reports 12 %.
    assert detector.type_for(5) is OutputType.POSITION
    # Other floors only reported 0 so far → not decidable.
    assert detector.type_for(6) is OutputType.UNKNOWN
    guest = next(o for o in outputs if o.room_id == 18)
    assert guest.percent == 12.0
    assert guest.open_fraction == pytest.approx(0.12)


def test_detection_accumulates_across_polls() -> None:
    detector = OutputTypeDetector()
    _outputs("outs_pro_a.json", detector)
    _outputs("outs_pro_b.json", detector)
    # Value 29 in outs_pro_b keeps floor 5 at POSITION; earlier evidence is not forgotten.
    assert detector.type_for(5) is OutputType.POSITION


def test_relay_values_never_trigger_position_detection() -> None:
    detector = OutputTypeDetector()
    _outputs("synthetic_outs_relay.json", detector)
    assert detector.type_for(6) is OutputType.UNKNOWN


def test_configured_type_wins() -> None:
    detector = OutputTypeDetector({6: OutputType.RELAY, 5: OutputType.UNKNOWN})
    outputs = _outputs("synthetic_outs_relay.json", detector)
    assert {o.percent for o in outputs} == {0.0, 100.0}
    kitchen = {o.number: o for o in outputs if o.room_id == 15}
    assert kitchen[1].percent == 100.0
    assert kitchen[1].open_fraction == 1.0
    assert kitchen[2].percent == 0.0
    # UNKNOWN in the configuration means "detect".
    detector.observe(5, 29)
    assert detector.type_for(5) is OutputType.POSITION


def test_configured_relay_is_not_overridden_by_large_value() -> None:
    detector = OutputTypeDetector({6: OutputType.RELAY})
    detector.observe(6, 29)
    assert detector.type_for(6) is OutputType.RELAY


def test_output_numbers_restart_per_floor_key_is_unique() -> None:
    outputs = _outputs("outs_pro_a.json", OutputTypeDetector())
    numbers = [o.number for o in outputs]
    keys = [o.key for o in outputs]
    assert len(set(numbers)) < len(numbers)
    assert len(set(keys)) == len(keys)


def test_leading_space_key_and_empty_outputs() -> None:
    raw = load_fixture("outs_pro_a.json")
    keys = {key for _, _, key, _ in iter_outputs(raw)}
    assert " 2" in keys
    outputs = _outputs("outs_pro_a.json", OutputTypeDetector())
    assert (1, 1, 2) in {o.key for o in outputs}
    # Rooms 24 and 26 have `ausgang: {}` and yield no outputs.
    assert not {o.room_id for o in outputs} & {24, 26}


def test_observe_outputs() -> None:
    detector = OutputTypeDetector()
    detector.observe_outputs([Output(8, 24, 1, 55, OutputType.UNKNOWN)])
    assert detector.type_for(8) is OutputType.POSITION


def test_unknown_type_has_no_percent() -> None:
    output = Output(6, 15, 1, 1, OutputType.UNKNOWN)
    assert output.percent is None
    assert output.open_fraction is None
