from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from conftest import FIXTURES, load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.models import WINDOW_OPEN_OFFSET_SOURCE, Offset, RoomDetails
from aiocontrome.parsers import parse_room_details

BERLIN = ZoneInfo("Europe/Berlin")
WINDOW_SEQUENCE = (
    "room_details_window_0_closed_pv_boost.json",
    "room_details_window_1_open_10min.json",
    "room_details_window_2_open_20min.json",
    "room_details_window_3_closed_again.json",
)


def _rooms(name: str) -> dict[int, RoomDetails]:
    return {r.id: r for r in parse_room_details(load_fixture(name), BERLIN)}


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("room_details_*.json")), ids=lambda p: p.name)
def test_all_fixtures_parse(path: Path) -> None:
    rooms = parse_room_details(load_fixture(path.name), BERLIN)
    assert len(rooms) == 11
    assert {r.operating_mode for r in rooms} == {"Heating"}
    assert all(r.gateway_offline_minutes is None for r in rooms)


def test_normal_room() -> None:
    office = _rooms("room_details_morning.json")[1]
    assert office.room_key == "room-001"
    assert office.floor_key == "floor-01"
    assert office.name == "Büro"
    assert office.icon == "desk"
    assert office.setpoint == 21.0
    assert office.permanent_setpoint == 21.0
    assert office.temperature_state in {"below_target", "at_target", "above_target"}
    assert office.floorcore_mode == "Bad und Wellness"
    assert office.floorcore_state is None
    assert office.is_temporary_mode is False
    assert office.window_open is False
    active = office.active_mode
    assert active is not None
    assert (active.mode_id, active.text, active.setpoint) == (3, "Anwesenheit 2", 21.0)
    assert (active.module, active.priority, active.use_offsets) == ("temperaturszenen", 1, True)
    assert len(office.scenes) == 10
    assert [s.id for s in office.scenes if s.is_active] == [3]
    assert office.scenes[-1].name == "Rückreise "  # names are passed through unchanged


def test_scene_control_uses_absolute_due_time() -> None:
    control = _rooms("room_details_morning.json")[1].scene_control
    assert control is not None
    assert control.current_scene == "Anwesenheit 2"
    assert control.next_scene == "Abends"
    assert control.next_temperature == 19.7
    assert control.next_due_time == datetime(2026, 11, 13, 18, 30, tzinfo=BERLIN)
    assert control.own_schedule is False  # key missing → False
    assert not hasattr(control, "next_due_time_relative")


def test_scene_control_null_for_rooms_without_schedule() -> None:
    rooms = _rooms("room_details_morning.json")
    assert rooms[24].scene_control is None
    assert rooms[26].scene_control is None


def test_own_schedule() -> None:
    living = _rooms("room_details_own_schedule.json")[19]
    assert living.scene_control is not None
    assert living.scene_control.own_schedule is True
    assert living.scene_control.next_due_time is None
    assert living.active_mode is None
    others = _rooms("room_details_own_schedule.json")
    assert not any(
        r.scene_control and r.scene_control.own_schedule for i, r in others.items() if i != 19
    )


def test_smart_timing_states() -> None:
    timing = _rooms("room_details_morning.json")[14].scene_control.smart_timing  # type: ignore[union-attr]
    assert timing is not None
    assert timing.state == "rechtzeitig"
    assert timing.time == datetime(2026, 11, 13, 18, 30, tzinfo=BERLIN)
    assert timing.temperature == 20.3
    assert _rooms("room_details_morning.json")[1].scene_control.smart_timing is None  # type: ignore[union-attr]
    preheat = _rooms("room_details_window_3_closed_again.json")[19].scene_control
    assert preheat is not None and preheat.smart_timing is not None
    assert preheat.smart_timing.state == "vorheizen"


def test_timer_active_but_not_running() -> None:
    timer = _rooms("room_details_morning.json")[19].timer
    assert timer is not None
    assert timer.active is True
    assert timer.running is False  # running is the truth; end lies in the past
    assert timer.end == datetime(2026, 1, 2, 9, 0, tzinfo=BERLIN)
    assert timer.start == datetime(2026, 1, 1, 17, 0, tzinfo=BERLIN)
    assert timer.offset == -5.0
    assert timer.current_offset == 0.0
    assert timer.duration_minutes == 960


def test_idle_timer() -> None:
    timer = _rooms("room_details_morning.json")[24].timer
    assert timer is not None
    assert (timer.active, timer.running, timer.start, timer.end) == (False, False, None, None)


def test_offsets_vary_per_room_and_empty_api_is_dropped() -> None:
    rooms = _rooms("room_details_morning.json")
    assert "api" not in rooms[1].offsets
    assert WINDOW_OPEN_OFFSET_SOURCE in rooms[1].offsets
    assert WINDOW_OPEN_OFFSET_SOURCE not in rooms[26].offsets
    assert set(rooms[1].offsets) != set(rooms[26].offsets)


def test_pv_boost_fps_offsets() -> None:
    rooms = _rooms("room_details_window_0_closed_pv_boost.json")
    fps = {i: r.offsets["FPS"].room for i, r in rooms.items() if "FPS" in r.offsets}
    assert max(fps.values()) == 5.0
    assert min(v for v in fps.values() if v > 0) == 2.0
    assert rooms[20].dominant_offset_source == "fps"
    assert rooms[16].dominant_offset_source == "wetter"


def test_window_open_sequence() -> None:
    states = [_rooms(name)[23] for name in WINDOW_SEQUENCE]
    assert [r.window_open for r in states] == [False, True, True, False]
    assert [r.dominant_offset_source for r in states] == [
        "fps",
        "fenster_offen",
        "fenster_offen",
        "wetter",
    ]
    assert states[1].offsets[WINDOW_OPEN_OFFSET_SOURCE] == Offset(-10.0, 0.0)
    # The radio sensor reports rarely: the value does not change while the window stays open.
    assert states[1].current_temperature == states[2].current_temperature
    # Only room 23 had its window open.
    assert not any(r.window_open for i, r in _rooms(WINDOW_SEQUENCE[1]).items() if i != 23)


@pytest.mark.parametrize("base", ["room_details_morning", "room_details_own_schedule"])
def test_skip_loops_yields_same_structure(base: str) -> None:
    full = parse_room_details(load_fixture(f"{base}.json"), BERLIN)
    skipped = parse_room_details(load_fixture(f"{base}_skip_loops.json"), BERLIN)
    assert [(r.id, r.room_key, r.floor_key) for r in full] == [
        (r.id, r.room_key, r.floor_key) for r in skipped
    ]
    raw = load_fixture(f"{base}.json") + load_fixture(f"{base}_skip_loops.json")
    for floor in raw:
        for room in floor["rooms"]:
            assert room["heatingLoops"] == []
            assert room["sensors"] == []
            assert room["unassignedReturnSensors"] == []


def test_minimal_room_and_optional_blocks() -> None:
    data = [
        {
            "floorId": "floor-09",
            "rooms": [
                {
                    "id": 5,
                    "setpoint": 20,
                    "activeMode": "nope",
                    "sceneControl": {"smartTiming": {"zeit": "bad", "temperatur": 20}},
                    "timer": None,
                    "gatewayOfflineMinutes": 12,
                    "dominantOffsetSource": "neue_quelle",
                }
            ],
        }
    ]
    (room,) = parse_room_details(data, BERLIN)
    assert room.permanent_setpoint == 20.0
    assert room.active_mode is None
    assert room.timer is None
    assert room.scene_control is not None and room.scene_control.smart_timing is None
    assert room.gateway_offline_minutes == 12
    assert room.dominant_offset_source == "neue_quelle"
    assert room.icon is None


@pytest.mark.parametrize(
    "data",
    [
        {},
        [{"rooms": []}],
        [{"floorId": "f", "rooms": [{"id": 1}]}],
        [{"floorId": "f", "rooms": [{"id": 1, "setpoint": 20, "scenes": [{"id": 1}]}]}],
    ],
)
def test_invalid_shapes(data: object) -> None:
    with pytest.raises(ContromeResponseError, match="room_details/"):
        parse_room_details(data, BERLIN)


def test_temporary_mode() -> None:
    # Live test: set-ziel with the unchanged setpoint for 30 min in room 23.
    rooms = _rooms("room_details_temporary_mode.json")
    room = rooms[23]
    assert room.is_temporary_mode is True
    active = room.active_mode
    assert active is not None
    assert (active.mode_id, active.module, active.text) == (-1, "quickui", "14:50")
    assert active.use_offsets is False
    control = room.scene_control
    assert control is not None
    assert control.mode_end == datetime(2026, 11, 15, 14, 50, tzinfo=BERLIN)
    assert control.current_scene is None
    assert control.after_timer_scene == "Anwesenheit 1"
    assert control.after_timer_temperature == 19.0
    assert control.next_due_time == datetime(2026, 11, 15, 18, 30, tzinfo=BERLIN)
    assert room.timer is not None and room.timer.running is False
    assert not any(r.is_temporary_mode for i, r in rooms.items() if i != 23)


def test_dominant_offset_source_may_be_null_or_humidity() -> None:
    rooms = _rooms("room_details_temporary_mode.json")
    assert rooms[23].dominant_offset_source is None
    assert rooms[1].dominant_offset_source == "luftfeuchte"
    assert {r.dominant_offset_source for r in rooms.values()} >= {None, "luftfeuchte", "wetter"}


# --- API offsets (live test 2026-11-17: set-roomoffset +1 K on room 23) -------------------

API_OFFSET = "room_details_api_offset_active.json"


def test_api_offset_is_only_visible_in_room_details() -> None:
    # roomoffsets/ does not list API offsets: it stayed [] while room and house offsets were
    # active (observed live, not recorded -> synthetic fixture). The recorded responses after
    # set-offset with 0 are [] as well.
    assert load_fixture("synthetic_roomoffsets_active.json") == []
    assert load_fixture("roomoffsets_api.json") == []
    assert load_fixture("roomoffsets_after_house.json") == []
    assert _rooms(API_OFFSET)[23].offsets["api"] == Offset(room=1.0, house=0.0)


def test_api_offset_house_key_only_until_room_offset_was_set() -> None:
    # offsets["api"] is {"haus": x}; "raum" only appears once a room offset was set.
    raw = {r["id"]: r["offsets"]["api"] for f in load_fixture(API_OFFSET) for r in f["rooms"]}
    assert raw[23] == {"raum": 1.0, "haus": 0.0}
    assert all(api == {"haus": 0.0} for room_id, api in raw.items() if room_id != 23)
    rooms = _rooms(API_OFFSET)
    assert all(r.offsets["api"] == Offset(0.0, 0.0) for i, r in rooms.items() if i != 23)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("room_details_*.json")), ids=lambda p: p.name)
def test_total_offset_includes_all_sources(path: Path) -> None:
    for room in parse_room_details(load_fixture(path.name), BERLIN):
        summed = sum(o.room + o.house for o in room.offsets.values())
        assert room.total_offset == pytest.approx(summed, abs=0.011)
        if room.target_temperature is not None:
            expected = room.setpoint + room.total_offset
            assert room.target_temperature == pytest.approx(expected, abs=0.011)


def test_total_offset_contains_api_offset() -> None:
    room = _rooms(API_OFFSET)[23]
    assert room.offsets["Wetter"].room == pytest.approx(-0.4)
    assert room.total_offset == pytest.approx(-0.4 + 1.0)
    assert room.target_temperature == pytest.approx(18.8 + 0.6)


def test_dominant_offset_source_ignores_api_offset() -> None:
    # The API offset (+1 K) is the largest, yet the dominant source stays "wetter".
    room = _rooms(API_OFFSET)[23]
    assert abs(room.offsets["api"].room) > abs(room.offsets["Wetter"].room)
    assert room.dominant_offset_source == "wetter"


def test_offset_sources_vary_per_room() -> None:
    rooms = _rooms(API_OFFSET)
    assert "Kalender" in rooms[23].offsets
    assert "Kalender" not in rooms[1].offsets
    assert "Geolocation" not in rooms[18].offsets
    assert "Geolocation" in rooms[1].offsets


def test_unknown_offset_sources_are_kept() -> None:
    data = load_fixture(API_OFFSET)
    data[0]["rooms"][0]["offsets"]["Neue Quelle"] = {"raum": 0.5, "haus": 0.0}
    room = parse_room_details(data, BERLIN)[0]
    assert room.offsets["Neue Quelle"] == Offset(0.5, 0.0)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("room_details_*.json")), ids=lambda p: p.name)
def test_pseudonymized_scene_names(path: Path) -> None:
    expected = {
        16: "Anwesenheit 1",
        3: "Anwesenheit 2",
        11: "Anwesenheit 3",
        12: "Anwesenheit 4",
        13: "Anwesenheit 5",
    }
    for room in parse_room_details(load_fixture(path.name), BERLIN):
        for scene in room.scenes:
            if scene.id in expected:
                assert scene.name == expected[scene.id]
            assert not scene.name.startswith("Anwesenheit ") or scene.id in expected
