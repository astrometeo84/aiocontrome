"""Live tests against a real Controme Mini-Server, opt-in only (see docs/LIVE_TESTS.md).

Read-only, except one credential probe (``verify_credentials``: a POST to
``roomoffset/99999/``, a room that does not exist, with offset 0). Never run in CI or the dev
container; ``pytest`` deselects them by default (``-m "not live"``) and they skip without
``CONTROME_LIVE=1``/``CONTROME_HOST``.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable

import aiohttp
import pytest

from aiocontrome import ContromeAuthError, ContromeClient, ContromeError, RoomDetails

from .conftest import FIRMWARE_CHANGED, TZ, Credentials, LiveConfig, describe, fail, live_call

pytestmark = pytest.mark.live

UNKNOWN_HOUSE = 99


async def _room_details_without_auth(client: ContromeClient) -> tuple[RoomDetails, ...]:
    """``room_details/`` from a client without credentials (it sends no Basic Auth)."""
    try:
        return await client.get_room_details()
    except ContromeAuthError as err:  # type and status only, never the message (URL)
        message = f"{FIRMWARE_CHANGED}: room_details/ without credentials: {describe(err)}"
    except Exception as err:
        message = f"room_details/: {describe(err)}"
    fail(message)  # outside the except blocks: no exception chain in the report


async def _expect_error(
    what: str, call: Awaitable[None], expected: type[ContromeError], status: int
) -> None:
    """Expect ``expected`` with ``status``; report only type and status otherwise."""
    got = "success"
    try:
        await call
    except expected as err:
        if getattr(err, "status", None) == status:
            return
        got = describe(err)
    except Exception as err:  # any other error: type and status only
        got = describe(err)
    # Outside the except blocks: no exception chain (with the URL) in the report.
    fail(f"{what}: expected {expected.__name__} status={status}, got {got}")


# --- a. read and parse ----------------------------------------------------------------------


async def test_read_and_parse_all_endpoints(client: ContromeClient) -> None:
    await live_call("info/", client.get_info())
    house = await live_call("temps/", client.get_house())
    if not house.rooms:
        fail("temps/: house has 0 rooms")
    await live_call("outs/", client.get_outputs())
    await live_call("upcomingoffsets/", client.get_upcoming_offsets())
    await live_call("fps/", client.get_fps())
    await live_call("vtr/", client.get_vtr())
    await live_call("wetter_pro/", client.get_weather_pro())

    details = await _room_details_without_auth(client)
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


async def test_room_details_without_credentials_returns_data(client: ContromeClient) -> None:
    details = await _room_details_without_auth(client)
    if not details:
        fail(f"{FIRMWARE_CHANGED}: room_details/ without credentials returned 0 rooms")


async def test_unknown_house_id_returns_same_rooms(
    live_config: LiveConfig, session: aiohttp.ClientSession, client: ContromeClient
) -> None:
    """Observed on a one-house system with house ID 1 (2026-11-20); multi-house unknown."""
    if live_config.house_id != 1:
        pytest.skip("unknown-house guard only covers house 1 (observed on a one-house system)")
    house = await live_call("temps/", client.get_house())
    other = ContromeClient(session, live_config.host, timezone=TZ, house_id=UNKNOWN_HOUSE)
    error = ""
    try:
        unknown = await other.get_house()
    except Exception as err:  # type and status only
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


async def test_verify_credentials(
    live_config: LiveConfig, session: aiohttp.ClientSession, credentials: Credentials
) -> None:
    """``verify_credentials()``: right credentials pass, a random wrong password → 403.

    The probe is a POST to ``roomoffset/99999/`` (room does not exist, offset 0); no effect
    observed (before/after comparison of room_details/ around the run on 2026-11-20). A
    ``ContromeResponseError`` with the right credentials means the server answered something
    other than 404 with an empty body (e.g. the Django debug page of an unknown route).
    One failed login per run; no lockout has been observed so far.
    """
    username, password = credentials.username, credentials.password
    right = ContromeClient(
        session,
        live_config.host,
        timezone=TZ,
        house_id=live_config.house_id,
        username=username,
        password=password,
    )
    await live_call("verify_credentials with right credentials", right.verify_credentials())

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
        "verify_credentials with wrong password", wrong.verify_credentials(), ContromeAuthError, 403
    )
