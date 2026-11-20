"""Credential handling: Basic Auth fallback on room_details/ and verify_credentials().

Against the local fake server (127.0.0.1); never a real system. Live findings of 2026-11-20
(skill controme-api): read endpoints do not check credentials; roomoffset/99999/ with
offset=0.00 answers 404 with an empty body for right and 403 for wrong credentials.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from conftest import (
    TEST_PASSWORD,
    TEST_PASSWORD_SPECIAL,
    TEST_USER,
    FakeControme,
    api_path,
    assert_no_secrets,
    echo_page,
    load_fixture,
    set_path,
)

import aiocontrome
from aiocontrome import (
    ContromeAuthError,
    ContromeClient,
    ContromeConnectionError,
    ContromeNotFoundError,
    ContromeResponseError,
)
from aiocontrome.client import basic_auth_header
from aiocontrome.parsers import parse_room_details

BERLIN = ZoneInfo("Europe/Berlin")
BASIC_TEST = "Basic " + base64.b64encode(f"{TEST_USER}:{TEST_PASSWORD}".encode()).decode()
ROOM_DETAILS = api_path("room_details")
PROBE = set_path("roomoffset/99999")


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


def _client(
    session: aiohttp.ClientSession,
    server: FakeControme,
    *,
    username: str | None = TEST_USER,
    password: str | None = TEST_PASSWORD,
    house_id: int | None = 1,
    request_timeout: float = 10.0,
) -> ContromeClient:
    return ContromeClient(
        session,
        server.host,
        timezone=BERLIN,
        house_id=house_id,
        username=username,
        password=password,
        request_timeout=request_timeout,
    )


async def _room_details(client: ContromeClient, how: str) -> Any:
    if how == "get_room_details":
        return await client.get_room_details()
    return await client.get_raw("room_details")


def test_basic_auth_header_is_exported() -> None:
    assert "basic_auth_header" in aiocontrome.__all__
    assert aiocontrome.basic_auth_header is basic_auth_header


# --- room_details/: no Basic Auth, fallback once after 401/403 --------------------------

READ_METHODS = pytest.mark.parametrize("how", ["get_room_details", "get_raw"])


@READ_METHODS
@pytest.mark.parametrize("status", [401, 403])
async def test_fallback_retries_once_with_basic_auth(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    caplog: pytest.LogCaptureFixture,
    how: str,
    status: int,
) -> None:
    controme_server.add_auth_error(ROOM_DETAILS, status)
    controme_server.add_fixture(ROOM_DETAILS, "room_details_morning.json")
    caplog.set_level("DEBUG", logger="aiocontrome")
    result = await _room_details(_client(session, controme_server), how)
    if how == "get_raw":
        assert result == load_fixture("room_details_morning.json")
    else:
        assert result == parse_room_details(load_fixture("room_details_morning.json"), BERLIN)
    assert [r.authorization for r in controme_server.requests] == [None, BASIC_TEST]
    assert "retrying once with Basic Auth" in caplog.text
    assert_no_secrets(caplog.text, TEST_USER, TEST_PASSWORD)


@READ_METHODS
@pytest.mark.parametrize(("first", "second"), [(401, 403), (403, 403), (403, 401)])
async def test_fallback_rejected_again_raises_auth_error(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    how: str,
    first: int,
    second: int,
) -> None:
    controme_server.add_auth_error(ROOM_DETAILS, first)
    controme_server.add_auth_error(ROOM_DETAILS, second)
    with pytest.raises(ContromeAuthError) as exc:
        await _room_details(_client(session, controme_server), how)
    assert exc.value.status == second
    assert [r.authorization for r in controme_server.requests] == [None, BASIC_TEST]


@READ_METHODS
@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize(
    ("username", "password"), [(None, None), (TEST_USER, None)], ids=["none", "user_only"]
)
async def test_no_fallback_without_credentials(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    how: str,
    status: int,
    username: str | None,
    password: str | None,
) -> None:
    controme_server.add_auth_error(ROOM_DETAILS, status)
    client = _client(session, controme_server, username=username, password=password)
    with pytest.raises(ContromeAuthError) as exc:
        await _room_details(client, how)
    assert exc.value.status == status
    assert [r.authorization for r in controme_server.requests] == [None]


@READ_METHODS
async def test_no_fallback_on_404(
    session: aiohttp.ClientSession, controme_server: FakeControme, how: str
) -> None:
    controme_server.add_not_found(ROOM_DETAILS)
    with pytest.raises(ContromeNotFoundError):
        await _room_details(_client(session, controme_server), how)
    assert len(controme_server.requests) == 1


@pytest.mark.parametrize("status", [401, 403])
async def test_no_fallback_on_other_read_endpoints(
    session: aiohttp.ClientSession, controme_server: FakeControme, status: int
) -> None:
    controme_server.add_auth_error(api_path("temps"), status)
    with pytest.raises(ContromeAuthError):
        await _client(session, controme_server).get_house()
    assert [r.authorization for r in controme_server.requests] == [None]


@pytest.mark.parametrize("password", [TEST_PASSWORD, TEST_PASSWORD_SPECIAL])
async def test_fallback_error_body_is_redacted(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    caplog: pytest.LogCaptureFixture,
    password: str,
) -> None:
    # The retry with Basic Auth is rejected with a page echoing the credentials.
    controme_server.add_auth_error(ROOM_DETAILS, 403)
    controme_server.add(ROOM_DETAILS, status=403, body=echo_page(TEST_USER, password))
    caplog.set_level("DEBUG", logger="aiocontrome")
    with pytest.raises(ContromeAuthError) as exc:
        await _client(session, controme_server, password=password).get_room_details()
    assert "**REDACTED**" in str(exc.value)
    assert_no_secrets(str(exc.value), TEST_USER, password)
    assert_no_secrets(caplog.text, TEST_USER, password)


# --- verify_credentials() ---------------------------------------------------------------


@pytest.mark.parametrize("body", ["", " \n"], ids=["empty", "whitespace"])
async def test_verify_credentials_valid(
    session: aiohttp.ClientSession, controme_server: FakeControme, body: str
) -> None:
    controme_server.add(PROBE, status=404, body=body)
    assert await _client(session, controme_server).verify_credentials() is None
    (request,) = controme_server.requests
    assert (request.method, request.path) == ("POST", "/set/json/v1/1/roomoffset/99999/")
    assert request.content_type == "application/x-www-form-urlencoded"
    assert request.authorization is None
    # Exactly the values tested live on 2026-11-20.
    assert request.form == {
        "user": TEST_USER,
        "password": TEST_PASSWORD,
        "offset": "0.00",
        "offset_name": "insights_probe",
    }


@pytest.mark.parametrize("password", [TEST_PASSWORD, TEST_PASSWORD_SPECIAL])
@pytest.mark.parametrize("echo", [False, True], ids=["empty_body", "echo_body"])
async def test_verify_credentials_rejected(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    caplog: pytest.LogCaptureFixture,
    password: str,
    echo: bool,
) -> None:
    controme_server.add(PROBE, status=403, body=echo_page(TEST_USER, password) if echo else "")
    caplog.set_level("DEBUG", logger="aiocontrome")
    with pytest.raises(ContromeAuthError) as exc:
        await _client(session, controme_server, password=password).verify_credentials()
    assert exc.value.status == 403
    assert str(exc.value) == "credentials rejected (HTTP 403)"
    assert_no_secrets(caplog.text, TEST_USER, password)


@pytest.mark.parametrize("password", [TEST_PASSWORD, TEST_PASSWORD_SPECIAL])
@pytest.mark.parametrize(
    ("status", "page"),
    [
        (404, "echo"),  # unknown route: Django debug page (here echoing the credentials)
        (404, "debug"),  # synthetic Django 404 debug page
        (200, ""),  # room 99999 would exist
        (401, ""),  # only 403 was observed live
        (500, "echo"),
    ],
)
async def test_verify_credentials_unverifiable(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    caplog: pytest.LogCaptureFixture,
    password: str,
    status: int,
    page: str,
) -> None:
    if page == "debug":
        controme_server.add_not_found(PROBE)
    else:
        body = echo_page(TEST_USER, password) if page == "echo" else ""
        controme_server.add(PROBE, status=status, body=body, content_type="text/html")
    caplog.set_level("DEBUG", logger="aiocontrome")
    with pytest.raises(ContromeResponseError) as exc:
        await _client(session, controme_server, password=password).verify_credentials()
    assert type(exc.value) is ContromeResponseError  # neither auth nor not-found error
    assert exc.value.status == status
    assert str(exc.value) == "credentials could not be verified"  # no body, no URL
    assert_no_secrets(caplog.text, TEST_USER, password)


@pytest.mark.parametrize(
    ("username", "password"),
    [(None, None), (TEST_USER, None), (None, TEST_PASSWORD)],
    ids=["none", "user_only", "password_only"],
)
async def test_verify_credentials_without_credentials_sends_nothing(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    username: str | None,
    password: str | None,
) -> None:
    client = _client(session, controme_server, username=username, password=password, house_id=None)
    with pytest.raises(ContromeAuthError, match="requires username and password"):
        await client.verify_credentials()
    assert controme_server.requests == []  # not even house detection


async def test_verify_credentials_timeout(
    session: aiohttp.ClientSession,
    controme_server: FakeControme,
    caplog: pytest.LogCaptureFixture,
) -> None:
    controme_server.add(PROBE, status=404, body="", delay=0.5)
    caplog.set_level("DEBUG", logger="aiocontrome")
    with pytest.raises(ContromeConnectionError, match="Timeout") as exc:
        await _client(session, controme_server, request_timeout=0.1).verify_credentials()
    assert_no_secrets(str(exc.value), TEST_USER, TEST_PASSWORD)
    assert_no_secrets(caplog.text, TEST_USER, TEST_PASSWORD)


async def test_verify_credentials_detects_house_id_first(
    session: aiohttp.ClientSession, controme_server: FakeControme
) -> None:
    controme_server.add(api_path("temps", 1), [])
    controme_server.add_fixture(api_path("temps", 2), "temps.json")
    controme_server.add(set_path("roomoffset/99999", 2), status=404, body="")
    client = _client(session, controme_server, house_id=None)
    assert await client.verify_credentials() is None
    assert client.house_id == 2
    assert controme_server.requests[-1].path == "/set/json/v1/2/roomoffset/99999/"
