"""Async client for the local Controme HTTP API (read endpoints)."""

from __future__ import annotations

import base64
import json
import logging
import math
from collections.abc import Mapping
from datetime import tzinfo
from typing import Any, Final, Literal

import aiohttp

from .errors import (
    ContromeAuthError,
    ContromeConnectionError,
    ContromeError,
    ContromeResponseError,
    body_excerpt,
    error_for_status,
)
from .models import (
    Fps,
    House,
    OperatingMode,
    Output,
    OutputType,
    ReturnSensor,
    RoomDetails,
    SystemInfo,
    UpcomingOffsets,
)
from .outputs import OutputTypeDetector
from .parsers import (
    parse_fps,
    parse_info,
    parse_outs,
    parse_rltemps,
    parse_room_details,
    parse_temps,
    parse_upcoming_offsets,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10.0
"""Seconds per request."""
MAX_HOUSE_ID = 10
"""Highest house ID tried by ``detect_house_id``."""
DEFAULT_DURATION: Final = "default"
"""Use the configured default duration (see ``set_default_duration``)."""
type Duration = int | Literal["default"]
"""Duration in minutes, or ``DEFAULT_DURATION``."""

_ERROR_BODY_READ_LIMIT = 1024
"""Bytes read from error responses (404 pages are ~240 kB; only an excerpt is kept)."""


class ContromeClient:
    """Client for one Controme Mini-Server.

    The caller owns ``session``. ``timezone`` is the local time zone of the Mini-Server; all
    local timestamps are converted with it. ``room_details`` requires ``username`` and
    ``password`` (HTTP Basic Auth); all other read endpoints need no credentials.

    If ``house_id`` is not given, it is detected on first use (see ``detect_house_id``).
    ``output_types`` configures the output type per floor; unconfigured floors are detected
    from the values seen across all ``get_outputs`` calls of this client.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        *,
        timezone: tzinfo,
        house_id: int | None = None,
        username: str | None = None,
        password: str | None = None,
        output_types: Mapping[int, OutputType] | None = None,
        request_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._base_url = _base_url(host)
        self._tz = timezone
        self._house_id = house_id
        self._credentials = (
            (username, password) if username is not None and password is not None else None
        )
        self._auth_header = (
            {"Authorization": basic_auth_header(username, password)}
            if username is not None and password is not None
            else None
        )
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)
        self.output_detector = OutputTypeDetector(output_types)

    @property
    def base_url(self) -> str:
        """Base URL of the Mini-Server, e.g. ``http://192.0.2.10``."""
        return self._base_url

    @property
    def house_id(self) -> int | None:
        """The configured or detected house ID (``None`` until detected)."""
        return self._house_id

    # --- read endpoints ---------------------------------------------------------------------

    async def get_info(self) -> SystemInfo:
        """System information (``info/``)."""
        return parse_info(await self._get("info", house_id=await self._house()), self._tz)

    async def get_house(self) -> House:
        """Floors, rooms and sensors with current values (``temps/``)."""
        house_id = await self._house()
        return parse_temps(
            await self._get("temps", house_id=house_id), house_id=house_id, tz=self._tz
        )

    async def get_outputs(self) -> tuple[Output, ...]:
        """Gateway outputs (``outs/``); types via ``output_detector``."""
        data = await self._get("outs", house_id=await self._house())
        return parse_outs(data, self.output_detector)

    async def get_return_sensors(self, room_id: int) -> tuple[ReturnSensor, ...]:
        """Return-flow sensors of a room (``rltemps/<room>/``). Prefer ``get_house``."""
        data = await self._get(f"rltemps/{int(room_id)}", house_id=await self._house())
        return parse_rltemps(data, self._tz)

    async def get_room_details(self) -> tuple[RoomDetails, ...]:
        """Detailed room state (``room_details/``, Basic Auth)."""
        if self._auth_header is None:
            raise ContromeAuthError("room_details requires username and password")
        data = await self._get("room_details", house_id=await self._house(), auth=True)
        return parse_room_details(data, self._tz)

    async def get_upcoming_offsets(self) -> UpcomingOffsets:
        """Upcoming heating program, timer and calendar changes (``upcomingoffsets/``)."""
        data = await self._get("upcomingoffsets", house_id=await self._house())
        return parse_upcoming_offsets(data, self._tz)

    async def get_fps(self) -> Mapping[int, Fps]:
        """Free programmable control blocks (``fps/``)."""
        return parse_fps(await self._get("fps", house_id=await self._house()), self._tz)

    # --- house ID ---------------------------------------------------------------------------

    async def detect_house_id(self) -> int:
        """Find the first house ID (1…``MAX_HOUSE_ID``) whose ``temps/`` contains rooms."""
        for house_id in range(1, MAX_HOUSE_ID + 1):
            try:
                data = await self._get("temps", house_id=house_id)
                house = parse_temps(data, house_id=house_id, tz=self._tz)
            except ContromeAuthError:
                raise
            except ContromeResponseError as err:  # incl. 404 and unexpected shapes
                _LOGGER.debug("House %s not usable: %s", house_id, err)
                continue
            if house.rooms:
                self._house_id = house_id
                return house_id
        raise ContromeError(f"No house with rooms found (tried IDs 1-{MAX_HOUSE_ID})")

    async def _house(self) -> int:
        if self._house_id is None:
            await self.detect_house_id()
        assert self._house_id is not None
        return self._house_id

    # --- write endpoints --------------------------------------------------------------------
    #
    # POST with form fields incl. `user`/`password` over plain HTTP (no TLS on the
    # Mini-Server): use only in the local network. Success = HTTP 2xx; the response body is
    # not evaluated (its format is not documented). Values are not range-checked on purpose:
    # the API documents no limits (cooling, offsets); callers apply plausibility limits.

    async def set_setpoint(self, room_id: int, setpoint: float) -> None:
        """Set the permanent setpoint of a room (``soll/<room>/``)."""
        await self._post(f"soll/{_id(room_id, 'room_id')}", {"soll": _number(setpoint)})

    async def set_target(self, room_id: int, target: float, *, duration: Duration) -> None:
        """Set a temporary target temperature (``ziel/<room>/``).

        ``duration`` (minutes or ``DEFAULT_DURATION``) is required by the API.
        """
        await self._post(
            f"ziel/{_id(room_id, 'room_id')}",
            {"ziel": _number(target), "duration": _duration(duration)},
        )

    async def set_scene(
        self, scene_id: int, *, room_id: int | None = None, duration: Duration | None = None
    ) -> None:
        """Activate a temperature scene (``temperaturszenen/<scene>/``).

        Without ``room_id`` the scene is activated in **all** rooms. Without ``duration`` it
        stays active until the next manual switch or heating program switch; with a duration
        (minutes or ``DEFAULT_DURATION``) it is activated temporarily and fixed.
        """
        fields: dict[str, str] = {}
        if room_id is not None:
            fields["room_id"] = str(_id(room_id, "room_id"))
        if duration is not None:
            fields["duration"] = _duration(duration)
        await self._post(f"temperaturszenen/{_id(scene_id, 'scene_id')}", fields)

    async def set_default_duration(self, minutes: int) -> None:
        """Set the default duration for temporary API commands and the Quick-UI (``quickui/``)."""
        await self._post("quickui", {"duration": _duration(minutes, allow_default=False)})

    async def set_operating_mode(self, mode: OperatingMode, *, room_id: int | None = None) -> None:
        """Switch the operating mode of one room, or of **all** rooms without ``room_id``."""
        endpoint = "rooms" if room_id is None else f"rooms/{_id(room_id, 'room_id')}"
        await self._post(endpoint, {"action": "betriebsart", "value": OperatingMode(mode).value})

    async def set_room_offset(self, room_id: int, offset: float, *, name: str) -> None:
        """Set an API offset (K) for a room (``roomoffset/<room>/``).

        Controme keeps the value only for **10 minutes** (cache); refresh it regularly.
        An offset of ``0`` removes it. Read it back via ``get_room_details()`` →
        ``offsets["api"]``; ``roomoffsets/`` does not list API offsets.
        """
        await self._post(
            f"roomoffset/{_id(room_id, 'room_id')}",
            {"offset": _number(offset), "offset_name": _name(name)},
        )

    async def set_house_offset(self, offset: float, *, name: str) -> None:
        """Set an API offset (K) for the whole house (``houseoffset/``).

        The official docs list this endpoint without parameters. The fields are **assumed** to
        match ``roomoffset`` (``offset``, ``offset_name``); the live test accepted them with
        HTTP 200 for ``0`` (= remove). The effect of a non-zero offset is not yet verified.
        """
        await self._post("houseoffset", {"offset": _number(offset), "offset_name": _name(name)})

    # --- HTTP -------------------------------------------------------------------------------

    def _url(self, endpoint: str, house_id: int, *, kind: str = "get") -> str:
        # Trailing slash matters on some endpoints; always send it.
        return f"{self._base_url}/{kind}/json/v1/{house_id}/{endpoint}/"

    async def _get(self, endpoint: str, *, house_id: int, auth: bool = False) -> Any:
        url = self._url(endpoint, house_id)
        text = await self._request(
            "GET", url, headers=self._auth_header if auth else None, data=None
        )
        try:
            return json.loads(text)
        except ValueError as err:
            raise ContromeResponseError(
                f"Invalid JSON from {url}: {body_excerpt(text)}", status=200
            ) from err

    async def _post(self, endpoint: str, fields: Mapping[str, str]) -> None:
        if self._credentials is None:
            raise ContromeAuthError("set methods require username and password")
        username, password = self._credentials
        url = self._url(endpoint, await self._house(), kind="set")
        await self._request(
            "POST", url, headers=None, data={"user": username, "password": password, **fields}
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None,
        data: Mapping[str, str] | None,
    ) -> str:
        """Send a request and return the body; never logs or raises with credentials."""
        try:
            async with self._session.request(
                method, url, headers=headers, data=data, timeout=self._timeout
            ) as response:
                _LOGGER.debug("%s %s → %s", method, url, response.status)
                if not 200 <= response.status < 300:
                    raw = await response.content.read(_ERROR_BODY_READ_LIMIT)
                    body = self._redact(raw.decode("utf-8", "replace"))
                    raise error_for_status(response.status, body)
                return await response.text()
        except TimeoutError as err:
            raise ContromeConnectionError(f"Timeout requesting {url}") from err
        except aiohttp.ClientError as err:
            message = self._redact(str(err))
            raise ContromeConnectionError(f"Error requesting {url}: {message}") from err

    def _redact(self, text: str) -> str:
        """Remove the password from text (e.g. a Django debug page echoing POST data)."""
        if self._credentials is not None and self._credentials[1]:
            return text.replace(self._credentials[1], "***")
        return text


def _id(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def _number(value: float) -> str:
    """Format a decimal for the API: dot as separator, two decimals."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"expected a finite number, got {value!r}")
    return f"{value:.2f}"


def _duration(value: Duration, *, allow_default: bool = True) -> str:
    if allow_default and value == DEFAULT_DURATION:
        return DEFAULT_DURATION
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        allowed = "positive minutes or DEFAULT_DURATION" if allow_default else "positive minutes"
        raise ValueError(f"duration must be {allowed}, got {value!r}")
    return str(value)


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("offset name must be a non-empty string")
    return value.strip()


def basic_auth_header(username: str, password: str) -> str:
    """Encode an HTTP Basic Auth header value (UTF-8).

    Built by hand: ``aiohttp.BasicAuth`` and the ``auth=`` request parameter are deprecated
    since aiohttp 3.14, and ``aiohttp.encode_basic_auth`` does not exist before 3.14.
    """
    if ":" in username:
        raise ValueError("username must not contain ':'")
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def _base_url(host: str) -> str:
    host = host.strip().rstrip("/")
    if not host:
        raise ValueError("host must not be empty")
    if "://" not in host:
        host = f"http://{host}"
    return host
