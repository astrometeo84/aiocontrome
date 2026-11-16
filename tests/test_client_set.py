"""Write-method tests against the local fake server (127.0.0.1); never a real system."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from conftest import FakeControme, api_path, set_path

from aiocontrome import (
    DEFAULT_DURATION,
    ContromeAuthError,
    ContromeClient,
    ContromeConnectionError,
    ContromeResponseError,
    OperatingMode,
)

BERLIN = ZoneInfo("Europe/Berlin")
PASSWORD = "s3cret-pw"
CREDENTIALS = {"user": "u", "password": PASSWORD}


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def client(session: aiohttp.ClientSession, controme_server: FakeControme) -> ContromeClient:
    return ContromeClient(
        session,
        controme_server.host,
        timezone=BERLIN,
        house_id=1,
        username="u",
        password=PASSWORD,
    )


async def _call_and_get_form(
    server: FakeControme, path: str, call: Awaitable[None]
) -> dict[str, str]:
    server.add_ok(path)
    await call
    (request,) = server.requests_to(path)
    assert request.method == "POST"
    assert request.content_type == "application/x-www-form-urlencoded"
    assert request.authorization is None  # credentials go into the form, not Basic Auth
    return request.form


# --- endpoints and form fields ----------------------------------------------------------


async def test_set_setpoint(client: ContromeClient, controme_server: FakeControme) -> None:
    form = await _call_and_get_form(
        controme_server, set_path("soll/3"), client.set_setpoint(3, 21.5)
    )
    assert form == {**CREDENTIALS, "soll": "21.50"}


@pytest.mark.parametrize(("duration", "expected"), [(90, "90"), (DEFAULT_DURATION, "default")])
async def test_set_target(
    client: ContromeClient, controme_server: FakeControme, duration: Any, expected: str
) -> None:
    form = await _call_and_get_form(
        controme_server, set_path("ziel/3"), client.set_target(3, 19, duration=duration)
    )
    assert form == {**CREDENTIALS, "ziel": "19.00", "duration": expected}


async def test_set_scene_permanent_for_all_rooms(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    form = await _call_and_get_form(
        controme_server, set_path("temperaturszenen/4"), client.set_scene(4)
    )
    assert form == CREDENTIALS


async def test_set_scene_temporary_for_one_room(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    form = await _call_and_get_form(
        controme_server,
        set_path("temperaturszenen/4"),
        client.set_scene(4, room_id=19, duration=DEFAULT_DURATION),
    )
    assert form == {**CREDENTIALS, "room_id": "19", "duration": "default"}


async def test_set_default_duration(client: ContromeClient, controme_server: FakeControme) -> None:
    form = await _call_and_get_form(
        controme_server, set_path("quickui"), client.set_default_duration(120)
    )
    assert form == {**CREDENTIALS, "duration": "120"}


@pytest.mark.parametrize("mode", list(OperatingMode))
async def test_set_operating_mode_single_room(
    client: ContromeClient, controme_server: FakeControme, mode: OperatingMode
) -> None:
    form = await _call_and_get_form(
        controme_server, set_path("rooms/19"), client.set_operating_mode(mode, room_id=19)
    )
    assert form == {**CREDENTIALS, "action": "betriebsart", "value": mode.value}


async def test_set_operating_mode_all_rooms_accepts_string(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    form = await _call_and_get_form(
        controme_server,
        set_path("rooms"),
        client.set_operating_mode("off"),  # type: ignore[arg-type]
    )
    assert form == {**CREDENTIALS, "action": "betriebsart", "value": "off"}


async def test_set_room_offset(client: ContromeClient, controme_server: FakeControme) -> None:
    form = await _call_and_get_form(
        controme_server,
        set_path("roomoffset/23"),
        client.set_room_offset(23, -1.25, name=" pv_boost "),
    )
    assert form == {**CREDENTIALS, "offset": "-1.25", "offset_name": "pv_boost"}


async def test_set_house_offset(client: ContromeClient, controme_server: FakeControme) -> None:
    form = await _call_and_get_form(
        controme_server, set_path("houseoffset"), client.set_house_offset(2, name="pv")
    )
    assert form == {**CREDENTIALS, "offset": "2.00", "offset_name": "pv"}


async def test_response_body_is_ignored(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_ok(set_path("soll/3"), body="<html>whatever</html>")
    assert await client.set_setpoint(3, 20) is None


async def test_house_id_is_detected_before_writing(
    session: aiohttp.ClientSession, controme_server: FakeControme
) -> None:
    client = ContromeClient(
        session, controme_server.host, timezone=BERLIN, username="u", password=PASSWORD
    )
    controme_server.add(api_path("temps", 1), [])
    controme_server.add_fixture(api_path("temps", 2), "temps.json")
    controme_server.add_ok(set_path("soll/3", house_id=2))
    await client.set_setpoint(3, 20)
    assert controme_server.requests[-1].path == set_path("soll/3", house_id=2)


# --- validation (nothing is sent) -------------------------------------------------------

Call = Callable[[ContromeClient], Awaitable[None]]


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda c: c.set_setpoint(3, float("nan")), id="nan"),
        pytest.param(lambda c: c.set_setpoint(3, float("inf")), id="inf"),
        pytest.param(lambda c: c.set_setpoint(3, True), id="bool-value"),
        pytest.param(lambda c: c.set_setpoint(3, "21"), id="string-value"),
        pytest.param(lambda c: c.set_setpoint(0, 21), id="room-zero"),
        pytest.param(lambda c: c.set_setpoint(True, 21), id="room-bool"),
        pytest.param(lambda c: c.set_target(3, 21, duration=0), id="duration-zero"),
        pytest.param(lambda c: c.set_target(3, 21, duration="later"), id="duration-text"),
        pytest.param(lambda c: c.set_target(3, 21, duration=1.5), id="duration-float"),
        pytest.param(lambda c: c.set_scene(4, room_id=-1), id="scene-room"),
        pytest.param(lambda c: c.set_scene(0), id="scene-zero"),
        pytest.param(lambda c: c.set_default_duration(DEFAULT_DURATION), id="quickui-default"),
        pytest.param(lambda c: c.set_operating_mode("auto"), id="mode"),
        pytest.param(lambda c: c.set_room_offset(3, 1, name="  "), id="empty-name"),
        pytest.param(lambda c: c.set_house_offset(1, name=None), id="name-none"),
    ],
)
async def test_invalid_arguments_raise_before_sending(
    client: ContromeClient, controme_server: FakeControme, call: Call
) -> None:
    with pytest.raises(ValueError):
        await call(client)
    assert controme_server.requests == []


async def test_no_range_limits(client: ContromeClient, controme_server: FakeControme) -> None:
    # The API documents no limits (cooling, offsets); plausibility is up to the caller.
    form = await _call_and_get_form(
        controme_server, set_path("soll/3"), client.set_setpoint(3, -40)
    )
    assert form["soll"] == "-40.00"


# --- auth, errors and credential hygiene ------------------------------------------------


async def test_missing_credentials_send_nothing(
    session: aiohttp.ClientSession, controme_server: FakeControme
) -> None:
    client = ContromeClient(session, controme_server.host, timezone=BERLIN, house_id=1)
    with pytest.raises(ContromeAuthError, match="username and password"):
        await client.set_setpoint(3, 21)
    assert controme_server.requests == []


async def test_403_on_wrong_credentials(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_auth_error(set_path("soll/3"), 403)
    with pytest.raises(ContromeAuthError) as exc:
        await client.set_setpoint(3, 21)
    assert exc.value.status == 403


async def test_password_never_in_errors_or_logs(
    client: ContromeClient, controme_server: FakeControme, caplog: pytest.LogCaptureFixture
) -> None:
    # A Django debug page may echo the POST data; the password must be redacted.
    controme_server.add(
        set_path("soll/3"),
        status=500,
        body=f"<html>POST: user=u password={PASSWORD} soll=21</html>",
    )
    caplog.set_level("DEBUG", logger="aiocontrome")
    with pytest.raises(ContromeResponseError) as exc:
        await client.set_setpoint(3, 21)
    assert PASSWORD not in str(exc.value)
    assert "password=***" in str(exc.value)
    assert PASSWORD not in caplog.text


async def test_timeout_on_write(
    session: aiohttp.ClientSession, controme_server: FakeControme
) -> None:
    client = ContromeClient(
        session,
        controme_server.host,
        timezone=BERLIN,
        house_id=1,
        username="u",
        password=PASSWORD,
        request_timeout=0.05,
    )
    controme_server.add(set_path("soll/3"), body="", delay=0.5)
    with pytest.raises(ContromeConnectionError, match="Timeout") as exc:
        await client.set_setpoint(3, 21)
    assert PASSWORD not in str(exc.value)


async def test_connection_error_is_redacted(
    session: aiohttp.ClientSession, unused_host: str
) -> None:
    client = ContromeClient(
        session, unused_host, timezone=BERLIN, house_id=1, username="u", password=PASSWORD
    )
    with pytest.raises(ContromeConnectionError) as exc:
        await client.set_setpoint(3, 21)
    assert PASSWORD not in str(exc.value)


def test_redact_without_credentials(session: aiohttp.ClientSession) -> None:
    client = ContromeClient(session, "controme.test", timezone=BERLIN)
    assert client._redact("nothing to hide") == "nothing to hide"


# --- recorded live responses (tests/fixtures/write/) ------------------------------------


@pytest.mark.parametrize(
    ("fixture", "path", "call"),
    [
        ("write/soll_ok.txt", "soll/23", lambda c: c.set_setpoint(23, 19)),
        ("write/ziel_ok.txt", "ziel/23", lambda c: c.set_target(23, 19, duration=30)),
        ("write/roomoffset_ok.txt", "roomoffset/23", lambda c: c.set_room_offset(23, 0, name="t")),
        ("write/houseoffset_ok.txt", "houseoffset", lambda c: c.set_house_offset(0, name="t")),
    ],
    ids=["soll", "ziel", "roomoffset", "houseoffset"],
)
async def test_recorded_success_responses(
    client: ContromeClient, controme_server: FakeControme, fixture: str, path: str, call: Call
) -> None:
    # Success is HTTP 200 with an empty text/html body; only ziel answers with JSON.
    controme_server.add_recorded(set_path(path), fixture)
    assert await call(client) is None


async def test_recorded_403_has_empty_body(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_recorded(set_path("soll/23"), "write/soll_403.txt")
    with pytest.raises(ContromeAuthError) as exc:
        await client.set_setpoint(23, 19)
    assert str(exc.value) == "HTTP 403"
    assert exc.value.status == 403
