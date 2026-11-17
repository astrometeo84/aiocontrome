"""Tests for ``aiocontrome.redact`` (diagnostics redaction)."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

import pytest
from conftest import FIXTURES, load_fixture

from aiocontrome import REDACTED, redact

ID_LIKE = re.compile(
    r"[0-9a-f]{2}(?:_[0-9a-f]{2}){7}|[0-9a-f]{2}(?::[0-9a-f]{2}){3,5}", re.IGNORECASE
)


def _strings(data: Any) -> list[str]:
    if isinstance(data, dict):
        return [*data.keys(), *(s for v in data.values() for s in _strings(v))]
    if isinstance(data, list):
        return [s for v in data for s in _strings(v)]
    return [data] if isinstance(data, str) else []


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.name)
def test_no_identifier_survives_in_any_fixture(path: Any) -> None:
    redacted = redact(load_fixture(path.name))
    assert not [s for s in _strings(redacted) if ID_LIKE.search(s)]
    json.dumps(redacted)  # still serialisable


def test_temps_sensor_ids_become_typed_placeholders(temps: Any) -> None:
    redacted = redact(temps)
    names = {s["name"] for f in redacted for r in f["raeume"] for s in r["sensoren"]}
    kinds = {re.sub(r"_\d+\*\*$", "", n).strip("*") for n in names}
    assert kinds == {
        "onewire_temperature",
        "onewire_humidity",
        "radio_room_controller",
        "radio_sensor",
        "virtual",
    }
    # Everything except the IDs is untouched (names, descriptions, values, timestamps).
    original = [s for f in temps for r in f["raeume"] for s in r["sensoren"]]
    result = [s for f in redacted for r in f["raeume"] for s in r["sensoren"]]
    for before, after in zip(original, result, strict=True):
        assert {k: v for k, v in after.items() if k != "name"} == {
            k: v for k, v in before.items() if k != "name"
        }
    assert [r["name"] for f in redacted for r in f["raeume"]] == [
        r["name"] for f in temps for r in f["raeume"]
    ]


def test_same_id_same_placeholder_across_responses(temps: Any) -> None:
    redacted = redact({"temps": temps, "rltemps/19": load_fixture("rltemps_19.json")})
    by_description = {
        s["beschreibung"]: s["name"]
        for f in redacted["temps"]
        for r in f["raeume"]
        for s in r["sensoren"]
    }
    for sensor in redacted["rltemps/19"]:
        assert sensor["name"] == by_description[sensor["beschreibung"]]
        assert sensor["name"].startswith("**onewire_temperature_")


def test_placeholders_are_numbered_per_type() -> None:
    data = ["28_00_00_00_00_00_00_01", "28_00_00_00_00_00_00_02", "05:00:00:01"]
    data.append(data[0].upper())  # IDs are case-insensitive
    assert redact(data) == [
        "**onewire_temperature_1**",
        "**onewire_temperature_2**",
        "**radio_sensor_1**",
        "**onewire_temperature_1**",
    ]


def test_ids_in_keys_and_inside_text_are_replaced() -> None:
    data = {
        "02:00:00:00:00:01": {"text": "Sensor 28_00_00_00_00_00_05_00 is offline"},
        "formula": "max(05:00:00:01, 3b_00_00_00_00_00_00_07)",
    }
    assert redact(data) == {
        "**radio_room_controller_1**": {"text": "Sensor **onewire_temperature_1** is offline"},
        "formula": "max(**radio_sensor_1**, **unknown_1**)",
    }


def test_mac_is_not_split_into_shorter_matches() -> None:
    assert redact("aa:bb:cc:dd:ee:ff") == "**radio_room_controller_1**"
    assert redact("aa:bb:cc:dd:ee") == "aa:bb:cc:dd:ee"  # 5 bytes: no known ID


@pytest.mark.parametrize(
    "text",
    [
        "14:50",
        "14:50:00",
        "10:49:32 13.11.2026",
        "2026-11-15 14:50",
        "2026-11-13T18:30:00.684+01:00",
        "Gästeklo",
        "wohnzimmer_rl",
        "v1.2.3",
        "Debian 11",
    ],
)
def test_ordinary_text_is_kept(text: str) -> None:
    assert redact(text) == text


def test_ipv4_addresses_are_redacted() -> None:
    page = "Request URL: http://192.0.2.10/get/json/v1/1/x/ from 198.51.100.7"
    assert redact(page) == f"Request URL: http://{REDACTED}/get/json/v1/1/x/ from {REDACTED}"


def test_sensitive_keys_case_insensitive_and_nested() -> None:
    data = {"Password": "s3cret", "nested": [{"host": "controme.local", "USER": "u"}], "ip": None}
    assert redact(data) == {
        "Password": REDACTED,
        "nested": [{"host": REDACTED, "USER": REDACTED}],
        "ip": None,
    }


def test_custom_keys_replace_defaults() -> None:
    data = {"password": "x", "seriennummer": "123"}
    assert redact(data, keys={"seriennummer"}) == {"password": "x", "seriennummer": REDACTED}


def test_input_is_not_modified_and_types_are_kept(temps: Any) -> None:
    before = copy.deepcopy(temps)
    redact(temps)
    assert temps == before
    assert redact((1, 2.5, True, None)) == [1, 2.5, True, None]
