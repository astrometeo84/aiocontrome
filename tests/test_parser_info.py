from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from conftest import load_fixture

from aiocontrome.errors import ContromeResponseError
from aiocontrome.parsers import parse_info

BERLIN = ZoneInfo("Europe/Berlin")


def test_parse_info() -> None:
    info = parse_info(load_fixture("info.json"), BERLIN)
    assert info.repo == "controme-core"
    assert info.branch == "uiv2"
    assert info.commit == "00744075"
    assert info.sw_date == datetime(2026, 11, 2, 13, 46, 52, tzinfo=BERLIN)
    assert info.hardware.startswith("Raspberry Pi 4")
    assert info.os.startswith("Debian")
    assert info.services_package is True
    assert info.app_compatible is True
    assert info.fbi == "Fri Apr 11 09:58:27 2025"


def test_parse_info_tolerates_missing_fields() -> None:
    info = parse_info({}, BERLIN)
    assert info.repo == ""
    assert info.sw_date is None
    assert info.services_package is False


def test_parse_info_rejects_list() -> None:
    with pytest.raises(ContromeResponseError):
        parse_info([], BERLIN)
