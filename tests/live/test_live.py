"""Live tests against a real Controme Mini-Server, opt-in only (see docs/LIVE_TESTS.md).

Read-only, except one credential probe (``set_room_offset`` on a room that does not exist,
offset 0). Never run in CI or the dev container; ``pytest`` deselects them by default
(``-m "not live"``) and they skip without ``CONTROME_LIVE=1``/``CONTROME_HOST``.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable
from typing import Any

import aiohttp
import pytest

from aiocontrome import (
    ContromeAuthError,
    ContromeClient,
    ContromeError,
    ContromeNotFoundError,
    RoomDetails,
)
from aiocontrome.parsers import parse_room_details

from .conftest import FIRMWARE_CHANGED, TZ, LiveConfig, describe, fail, live_call

pytestmark = pytest.mark.live

PROBE_ROOM = 99999
"""A room ID that does not exist (live test 2026-11-20)."""
UNKNOWN_HOUSE = 99


async def _room_details_without_auth(
    session: aiohttp.ClientSession, config: LiveConfig, client: ContromeClient
) -> tuple[RoomDetails, ...]:
    """``room_details/`` requested without any credentials.

    Until aiocontrome 0.3.0, ``get_room_details()`` and ``get_raw("room_details")`` refuse to
    run without credentials (client-side ``ContromeAuthError``), so this one request goes
    through a plain aiohttp GET plus the public parser. Simplify to ``get_room_details()`` on a
    client without credentials once 0.3.0 no longer sends Basic Auth on reads.
    """
    url = f"{client.base_url}/get/json/v1/{config.house_id}/room_details/"
    message = ""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            status = response.status
            data: Any = await response.json(content_type=None) if status == 200 else None
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        message = f"room_details/ without credentials: {describe(err)}"
    if message:
        fail(message)
    if status != 200:
        fail(f"{FIRMWARE_CHANGED}: room_details/ without credentials answered status={status}")
    try:
        return parse_room_details(data, TZ)
    except ContromeError as err:
        message = f"parse room_details/: {describe(err)}"
    fail(message)


async def _expect_error(
    what: str, call: Awaitable[None], expected: type[ContromeError], status: int
) -> None:
    got = "success"
    try:
        await call
    except expected as err:
        if getattr(err, "status", None) == status:
            return
        got = describe(err)
    except (ContromeError, aiohttp.ClientError, TimeoutError) as err:
        got = describe(err)
    # Outside the except blocks: no exception chain (with the URL) in the report.
    fail(f"{what}: expected {expected.__name__} status={status}, got {got}")


# --- a. read and parse ----------------------------------------------------------------------


async def test_read_and_parse_all_endpoints(
    live_config: LiveConfig, session: aiohttp.ClientSession, client: ContromeClient
) -> None:
    await live_call("info/", client.get_info())
    house = await live_call("temps/", client.get_house())
    if not house.rooms:
        fail("temps/: house has 0 rooms")
    await live_call("outs/", client.get_outputs())
    await live_call("upcomingoffsets/", client.get_upcoming_offsets())
    await live_call("fps/", client.get_fps())
    await live_call("vtr/", client.get_vtr())
    await live_call("wetter_pro/", client.get_weather_pro())

    details = await _room_details_without_auth(session, live_config, client)
    temps_ids = {room.id for room in house.rooms}
    details_ids = {room.id for room in details}
    if temps_ids != details_ids:
        fail(
            "room IDs of temps/ and room_details/ differ: "
            f"{len(temps_ids - details_ids)} only in temps/, "
            f"{len(details_ids - temps_ids)} only in room_details/, "
            f"{len(temps_ids & details_ids)} in both"
        )


async def test_return_sensors_of_first_room(client: ContromeClient) -> None:
    house = await live_call("temps/", client.get_house())
    room = next((r for r in house.rooms if r.return_sensors), None)
    if room is None:
        pytest.skip("no room with return-flow sensors on this system")
    sensors = await live_call("rltemps/<room>/", client.get_return_sensors(room.id))
    if not sensors:
        fail(f"rltemps/{room.id}/: 0 sensors, temps/ lists {len(room.return_sensors)}")


# --- b. guards for the observations of 2026-11-20 -----------------------------------------


async def test_room_details_without_credentials_returns_data(
    live_config: LiveConfig, session: aiohttp.ClientSession, client: ContromeClient
) -> None:
    details = await _room_details_without_auth(session, live_config, client)
    if not details:
        fail(f"{FIRMWARE_CHANGED}: room_details/ without credentials returned 0 rooms")


async def test_unknown_house_id_returns_same_rooms(
    live_config: LiveConfig, session: aiohttp.ClientSession, client: ContromeClient
) -> None:
    house = await live_call("temps/", client.get_house())
    other = ContromeClient(session, live_config.host, timezone=TZ, house_id=UNKNOWN_HOUSE)
    error = ""
    try:
        unknown = await other.get_house()
    except (ContromeError, aiohttp.ClientError, TimeoutError) as err:
        error = describe(err)
    if error:
        fail(f"{FIRMWARE_CHANGED}: temps/ with house {UNKNOWN_HOUSE}: {error}")
    expected = {room.id for room in house.rooms}
    got = {room.id for room in unknown.rooms}
    if got != expected:
        fail(
            f"{FIRMWARE_CHANGED}: temps/ with house {UNKNOWN_HOUSE} has {len(got)} rooms, "
            f"house {live_config.house_id} has {len(expected)}, {len(got & expected)} in common"
        )


# --- c. credential check via a write call without effect ----------------------------------


async def test_credential_probe(
    live_config: LiveConfig, session: aiohttp.ClientSession, credentials: tuple[str, str]
) -> None:
    """Check the credentials with ``set_room_offset(99999, 0)``.

    Room 99999 does not exist and offset 0 means "remove", so the call presumably has no
    effect (live test 2026-11-20, no before/after comparison). The server checks the
    credentials before the room: right credentials → 404 (empty body), wrong → 403.
    """
    username, password = credentials
    right = ContromeClient(
        session,
        live_config.host,
        timezone=TZ,
        house_id=live_config.house_id,
        username=username,
        password=password,
    )
    await _expect_error(
        "right credentials",
        right.set_room_offset(PROBE_ROOM, 0, name="insights_probe"),
        ContromeNotFoundError,
        404,
    )

    wrong_password = secrets.token_urlsafe(24)
    while wrong_password == password:  # pragma: no cover - practically impossible
        wrong_password = secrets.token_urlsafe(24)
    wrong = ContromeClient(
        session,
        live_config.host,
        timezone=TZ,
        house_id=live_config.house_id,
        username=username,
        password=wrong_password,
    )
    await _expect_error(
        "wrong password",
        wrong.set_room_offset(PROBE_ROOM, 0, name="insights_probe"),
        ContromeAuthError,
        403,
    )
