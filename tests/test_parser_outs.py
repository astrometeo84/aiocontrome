from __future__ import annotations

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.models import OutputType
from aiocontrome.outputs import OutputTypeDetector
from aiocontrome.parsers import parse_outs


def test_pro_gateway_positions() -> None:
    outputs = parse_outs(load_fixture("outs_pro_a.json"))
    by_key = {o.key: o for o in outputs}
    guest = by_key[(5, 18, 2)]
    assert guest.raw_value == 12
    assert guest.type is OutputType.POSITION
    assert guest.percent == 12.0
    # Floors without a value > 1 are not decidable from a single response.
    assert by_key[(6, 15, 1)].type is OutputType.UNKNOWN


def test_leading_space_keys_are_stripped() -> None:
    keys = {o.key for o in parse_outs(load_fixture("outs_pro_a.json"))}
    assert (1, 1, 2) in keys  # " 2" in Büro
    assert (6, 19, 2) in keys  # " 2" in Wohnzimmer


def test_numbers_restart_per_floor_and_keys_are_unique() -> None:
    outputs = parse_outs(load_fixture("outs_pro_a.json"))
    assert len(outputs) == 11
    assert len({o.key for o in outputs}) == 11
    assert sum(1 for o in outputs if o.number == 1) > 1


def test_rooms_without_outputs() -> None:
    outputs = parse_outs(load_fixture("outs_pro_a.json"))
    assert not {o.room_id for o in outputs} & {24, 26}


def test_shared_detector_keeps_evidence_across_polls() -> None:
    detector = OutputTypeDetector()
    parse_outs(load_fixture("outs_pro_a.json"), detector)
    second = parse_outs(load_fixture("outs_pro_b.json"), detector)
    assert detector.type_for(5) is OutputType.POSITION
    assert all(o.type is OutputType.POSITION for o in second if o.floor_id == 5)
    assert max(o.raw_value for o in second) == 29


def test_relay_gateway_with_configured_type() -> None:
    data = load_fixture("synthetic_outs_relay.json")
    assert {o.type for o in parse_outs(data)} == {OutputType.UNKNOWN}
    outputs = parse_outs(data, OutputTypeDetector({6: OutputType.RELAY}))
    by_key = {o.key: o for o in outputs}
    assert by_key[(6, 15, 1)].percent == 100.0
    assert by_key[(6, 15, 2)].percent == 0.0
    assert by_key[(6, 19, 3)].percent == 100.0


def test_non_numeric_entries_are_skipped() -> None:
    data = [{"id": 1, "raeume": [{"id": 2, "ausgang": {"x": 1, "3": None, "4": 50}}]}]
    outputs = parse_outs(data)
    assert [o.key for o in outputs] == [(1, 2, 4)]


@pytest.mark.parametrize("data", [{}, [{"raeume": []}], [{"id": 1, "raeume": [{}]}]])
def test_invalid_shapes(data: object) -> None:
    with pytest.raises(ContromeResponseError, match="outs/"):
        parse_outs(data)
