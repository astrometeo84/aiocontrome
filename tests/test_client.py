"""Client tests against the local fake server (127.0.0.1); never a real system."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from conftest import FakeControme, api_path, load_fixture

from aiocontrome import (
    ContromeAuthError,
    ContromeClient,
    ContromeConnectionError,
    ContromeError,
    ContromeNotFoundError,
    ContromeResponseError,
    OutputType,
)
from aiocontrome.client import MAX_HOUSE_ID, _base_url, basic_auth_header
from aiocontrome.errors import MAX_BODY_EXCERPT

BERLIN = ZoneInfo("Europe/Berlin")
BASIC_U_P = "Basic " + base64.b64encode(b"u:p").decode()


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def client(session: aiohttp.ClientSession, controme_server: FakeControme) -> ContromeClient:
    return ContromeClient(
        session, controme_server.host, timezone=BERLIN, house_id=1, username="u", password="p"
    )


@pytest.fixture
def auto_client(session: aiohttp.ClientSession, controme_server: FakeControme) -> ContromeClient:
    return ContromeClient(session, controme_server.host, timezone=BERLIN)


# --- construction -----------------------------------------------------------------------


def test_timezone_is_required_keyword(session: aiohttp.ClientSession) -> None:
    with pytest.raises(TypeError):
        ContromeClient(session, "controme.test")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        ContromeClient(session, "controme.test", BERLIN)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("controme.test", "http://controme.test"),
        (" controme.test/ ", "http://controme.test"),
        ("controme.test:8080", "http://controme.test:8080"),
        ("http://controme.test/", "http://controme.test"),
    ],
)
def test_base_url(host: str, expected: str) -> None:
    assert _base_url(host) == expected


def test_empty_host() -> None:
    with pytest.raises(ValueError, match="host"):
        _base_url(" ")


def test_basic_auth_header() -> None:
    assert basic_auth_header("u", "p") == BASIC_U_P
    # Passwords may contain ':' and non-ASCII characters (encoded as UTF-8).
    expected = "Basic " + base64.b64encode("u:pä:ss".encode()).decode()
    assert basic_auth_header("u", "pä:ss") == expected
    with pytest.raises(ValueError, match="':'"):
        basic_auth_header("u:x", "p")


# --- endpoints --------------------------------------------------------------------------


async def test_get_info(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add_fixture(api_path("info"), "info.json")
    info = await client.get_info()
    assert info.branch == "uiv2"
    assert info.sw_date == datetime(2026, 11, 2, 13, 46, 52, tzinfo=BERLIN)
    assert client.base_url == f"http://{controme_server.host}"


async def test_get_house_sends_no_auth(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_fixture(api_path("temps"), "temps.json")
    house = await client.get_house()
    assert house.id == 1
    assert len(house.rooms) == 11
    (request,) = controme_server.requests_to(api_path("temps"))
    assert request.method == "GET"
    assert request.authorization is None


async def test_get_outputs_keeps_detection_across_polls(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_fixture(api_path("outs"), "outs_pro_a.json")
    controme_server.add_fixture(api_path("outs"), "outs_pro_b.json")
    await client.get_outputs()
    second = await client.get_outputs()
    assert client.output_detector.type_for(5) is OutputType.POSITION
    assert {o.type for o in second if o.floor_id == 5} == {OutputType.POSITION}
    assert max(o.raw_value for o in second) == 29


async def test_configured_output_types(
    session: aiohttp.ClientSession, controme_server: FakeControme
) -> None:
    client = ContromeClient(
        session,
        controme_server.host,
        timezone=BERLIN,
        house_id=1,
        output_types={6: OutputType.RELAY},
    )
    controme_server.add_fixture(api_path("outs"), "synthetic_outs_relay.json")
    outputs = await client.get_outputs()
    assert {o.percent for o in outputs} == {0.0, 100.0}


async def test_get_return_sensors(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add_fixture(api_path("rltemps/23"), "rltemps_23.json")
    (sensor,) = await client.get_return_sensors(23)
    assert sensor.value == 24.94


async def test_get_room_details_uses_basic_auth(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_fixture(api_path("room_details"), "room_details_window_1_open_10min.json")
    rooms = await client.get_room_details()
    assert next(r for r in rooms if r.id == 23).window_open is True
    (request,) = controme_server.requests_to(api_path("room_details"))
    assert request.authorization == BASIC_U_P


async def test_get_room_details_without_credentials(
    session: aiohttp.ClientSession, controme_server: FakeControme
) -> None:
    client = ContromeClient(
        session, controme_server.host, timezone=BERLIN, house_id=1, username="u"
    )
    with pytest.raises(ContromeAuthError, match="username and password"):
        await client.get_room_details()
    assert controme_server.requests == []  # nothing was sent


async def test_get_upcoming_offsets(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add_fixture(api_path("upcomingoffsets"), "upcomingoffsets.json")
    upcoming = await client.get_upcoming_offsets()
    assert upcoming.houses[1]["heizprogramm"][0].target_id == 15


async def test_get_fps(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add_fixture(api_path("fps"), "fps.json")
    assert len(await client.get_fps()) == 11


@pytest.mark.parametrize(
    ("method", "endpoint", "fixture"),
    [
        ("get_vtr", "vtr", "vtr_empty.json"),
        ("get_weather_pro", "wetter_pro", "wetter_pro_empty.json"),
    ],
)
async def test_passthrough_endpoints(
    client: ContromeClient,
    controme_server: FakeControme,
    method: str,
    endpoint: str,
    fixture: str,
) -> None:
    # Responses for the same path are served in order.
    controme_server.add_fixture(api_path(endpoint), fixture)
    controme_server.add(api_path(endpoint), {"x": [1, {"y": 2}]})
    assert await getattr(client, method)() == {}
    assert await getattr(client, method)() == {"x": (1, {"y": 2})}


# --- raw access -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endpoint", "path", "fixture"),
    [
        ("temps", "temps", "temps.json"),
        ("/outs/", "outs", "outs_pro_a.json"),
        ("rltemps/19", "rltemps/19", "rltemps_19.json"),
        ("fps", "fps", "fps.json"),
    ],
)
async def test_get_raw_returns_unparsed_json(
    client: ContromeClient, controme_server: FakeControme, endpoint: str, path: str, fixture: str
) -> None:
    controme_server.add_fixture(api_path(path), fixture)
    assert await client.get_raw(endpoint) == load_fixture(fixture)
    (request,) = controme_server.requests_to(api_path(path))
    assert request.authorization is None


async def test_get_raw_room_details_uses_basic_auth(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_fixture(api_path("room_details"), "room_details_morning.json")
    assert await client.get_raw("room_details") == load_fixture("room_details_morning.json")
    (request,) = controme_server.requests_to(api_path("room_details"))
    assert request.authorization == BASIC_U_P


async def test_get_raw_room_details_without_credentials(
    auto_client: ContromeClient, controme_server: FakeControme
) -> None:
    with pytest.raises(ContromeAuthError, match="room_details requires"):
        await auto_client.get_raw("room_details")
    assert controme_server.requests == []


async def test_get_raw_returns_error_objects_unchanged(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_fixture(api_path("vtr"), "apiv1_disabled.json")
    assert (await client.get_raw("vtr"))["error"] == "api_disabled"


async def test_get_raw_http_errors_raise(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_broken_json(api_path("temps"))
    with pytest.raises(ContromeResponseError, match="Invalid JSON"):
        await client.get_raw("temps")
    with pytest.raises(ContromeNotFoundError):
        await client.get_raw("nope")


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "/",
        "../set/json",
        "temps/../info",
        "temps?x=1",
        "rltemps/0",
        "rltemps/abc",
        "Temps",
        "a b",
    ],
)
async def test_get_raw_rejects_invalid_endpoints(
    client: ContromeClient, controme_server: FakeControme, endpoint: str
) -> None:
    with pytest.raises(ValueError, match="Invalid endpoint"):
        await client.get_raw(endpoint)
    assert controme_server.requests == []


async def test_every_url_has_trailing_slash(
    client: ContromeClient, controme_server: FakeControme
) -> None:
    for endpoint in ("temps", "outs", "rltemps/1", "room_details"):
        controme_server.add(api_path(endpoint), [])
    for endpoint in ("upcomingoffsets", "fps"):
        controme_server.add(api_path(endpoint), {})
    await client.get_house()
    await client.get_outputs()
    await client.get_return_sensors(1)
    await client.get_room_details()
    await client.get_upcoming_offsets()
    await client.get_fps()
    assert len(controme_server.requests) == 6
    assert all(r.path.endswith("/") for r in controme_server.requests)


# --- errors -----------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors(
    client: ContromeClient, controme_server: FakeControme, status: int
) -> None:
    controme_server.add_auth_error(api_path("room_details"), status)
    with pytest.raises(ContromeAuthError) as exc:
        await client.get_room_details()
    assert exc.value.status == status


async def test_404_debug_page_is_not_logged_in_full(
    client: ContromeClient, controme_server: FakeControme, caplog: pytest.LogCaptureFixture
) -> None:
    controme_server.add_not_found(api_path("fps"), pad_to=240_000)
    caplog.set_level("DEBUG", logger="aiocontrome")
    with pytest.raises(ContromeNotFoundError) as exc:
        await client.get_fps()
    message = str(exc.value)
    assert message.startswith("HTTP 404: <!DOCTYPE html>")
    assert len(message) <= len("HTTP 404: ") + MAX_BODY_EXCERPT + 1
    assert "padding" not in caplog.text
    assert len(caplog.text) < 1_000


async def test_unknown_route_returns_404(client: ContromeClient) -> None:
    with pytest.raises(ContromeNotFoundError, match="Page not found"):
        await client.get_fps()


async def test_server_error(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add(api_path("fps"), status=500, body="boom", content_type="text/plain")
    with pytest.raises(ContromeResponseError, match="HTTP 500: boom") as exc:
        await client.get_fps()
    assert exc.value.status == 500


async def test_broken_json(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add_broken_json(api_path("fps"))
    with pytest.raises(ContromeResponseError, match="Invalid JSON"):
        await client.get_fps()


async def test_unexpected_shape(client: ContromeClient, controme_server: FakeControme) -> None:
    controme_server.add(api_path("temps"), {"unexpected": True})
    with pytest.raises(ContromeResponseError, match="temps/"):
        await client.get_house()


async def test_timeout(session: aiohttp.ClientSession, controme_server: FakeControme) -> None:
    client = ContromeClient(
        session, controme_server.host, timezone=BERLIN, house_id=1, request_timeout=0.05
    )
    controme_server.add_timeout(api_path("temps"), delay=0.5)
    with pytest.raises(ContromeConnectionError, match="Timeout"):
        await client.get_house()


async def test_connection_refused(session: aiohttp.ClientSession, unused_host: str) -> None:
    client = ContromeClient(session, unused_host, timezone=BERLIN, house_id=1)
    with pytest.raises(ContromeConnectionError, match="Error requesting"):
        await client.get_house()


# --- house ID detection -----------------------------------------------------------------


async def test_detect_house_id_first_with_rooms(
    auto_client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add(api_path("temps", 1), [])
    controme_server.add_not_found(api_path("temps", 2))
    controme_server.add_fixture(api_path("temps", 3), "temps.json")
    assert auto_client.house_id is None
    assert await auto_client.detect_house_id() == 3
    assert auto_client.house_id == 3


async def test_house_id_is_detected_lazily_once(
    auto_client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_fixture(api_path("temps", 1), "temps.json")
    controme_server.add_fixture(api_path("fps", 1), "fps.json")
    await auto_client.get_fps()
    await auto_client.get_fps()
    assert auto_client.house_id == 1
    assert len(controme_server.requests_to(api_path("temps", 1))) == 1


async def test_detect_house_id_none_found(
    auto_client: ContromeClient, controme_server: FakeControme
) -> None:
    for house_id in range(1, MAX_HOUSE_ID + 1):
        controme_server.add(api_path("temps", house_id), [{"id": 1, "raeume": []}])
    with pytest.raises(ContromeError, match="No house with rooms"):
        await auto_client.detect_house_id()
    assert len(controme_server.requests) == MAX_HOUSE_ID


async def test_detect_house_id_propagates_auth_errors(
    auto_client: ContromeClient, controme_server: FakeControme
) -> None:
    controme_server.add_auth_error(api_path("temps", 1), 403)
    with pytest.raises(ContromeAuthError):
        await auto_client.detect_house_id()


async def test_detect_house_id_propagates_connection_errors(
    session: aiohttp.ClientSession, unused_host: str
) -> None:
    client = ContromeClient(session, unused_host, timezone=BERLIN)
    with pytest.raises(ContromeConnectionError):
        await client.detect_house_id()
