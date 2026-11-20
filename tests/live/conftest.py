"""Configuration and helpers for the opt-in live tests (see docs/LIVE_TESTS.md).

Configured only through environment variables; without them every live test is skipped:

- ``CONTROME_LIVE=1`` (required) and ``CONTROME_HOST`` (required),
- ``CONTROME_HOUSE`` (optional, default 1),
- ``CONTROME_USER`` / ``CONTROME_PASSWORD`` (optional, only for the credential check).

Output rule: assertions and failure messages show only numbers, status codes, key names and
counts; never names, sensor IDs, MACs, the host or credentials. aiocontrome's exception
messages contain the request URL (host), so ``live_call`` reports only type and status.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass
from typing import NoReturn
from zoneinfo import ZoneInfo

import aiohttp
import pytest

from aiocontrome import ContromeClient, ContromeError

TZ = ZoneInfo("Europe/Berlin")
# Wording given by the maintainer (German, with an en dash).
FIRMWARE_CHANGED = "Firmware-Verhalten geändert – Skill controme-api prüfen"  # noqa: RUF001


@dataclass(frozen=True)
class LiveConfig:
    host: str
    house_id: int
    username: str | None
    password: str | None

    @property
    def has_credentials(self) -> bool:
        return bool(self.username) and bool(self.password)


def _read_config() -> LiveConfig | str:
    """The live configuration, or the reason why live tests are skipped."""
    if os.environ.get("CONTROME_LIVE") != "1":
        return "live tests disabled: CONTROME_LIVE=1 not set (see docs/LIVE_TESTS.md)"
    host = os.environ.get("CONTROME_HOST", "").strip()
    if not host:
        return "live tests disabled: CONTROME_HOST not set (see docs/LIVE_TESTS.md)"
    house = os.environ.get("CONTROME_HOUSE", "1").strip() or "1"
    if not house.isdigit() or int(house) < 1:
        return "live tests disabled: CONTROME_HOUSE must be a positive integer"
    return LiveConfig(
        host=host,
        house_id=int(house),
        username=os.environ.get("CONTROME_USER") or None,
        password=os.environ.get("CONTROME_PASSWORD") or None,
    )


@pytest.fixture
def live_config() -> LiveConfig:
    config = _read_config()
    if isinstance(config, str):
        pytest.skip(config)
    return config


@pytest.fixture
def credentials(live_config: LiveConfig) -> tuple[str, str]:
    """Username and password; skips the test if they are not configured."""
    if not live_config.has_credentials:
        pytest.skip("credential check skipped: CONTROME_USER/CONTROME_PASSWORD not set")
    assert live_config.username is not None and live_config.password is not None
    return live_config.username, live_config.password


@pytest.fixture
async def session(live_config: LiveConfig) -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def client(live_config: LiveConfig, session: aiohttp.ClientSession) -> ContromeClient:
    """Client without credentials for the configured house."""
    return ContromeClient(session, live_config.host, timezone=TZ, house_id=live_config.house_id)


def fail(message: str) -> NoReturn:
    """Fail without traceback (locals and exception texts could contain the host).

    Never call it inside an ``except`` block: Python would attach the caught exception as
    context, and pytest prints that chain (with the URL) even with ``pytrace=False``. Store
    the message in the ``except`` block and call ``fail`` after it.
    """
    pytest.fail(message, pytrace=False)


def describe(err: BaseException) -> str:
    """Exception type and HTTP status only, never the message (it contains the URL)."""
    status = getattr(err, "status", None)
    return type(err).__name__ + ("" if status is None else f" status={status}")


async def live_call[T](what: str, call: Awaitable[T]) -> T:
    """Await ``call``; on any error fail with ``what``, the exception type and status only."""
    try:
        return await call
    except (ContromeError, aiohttp.ClientError, TimeoutError, ValueError) as err:
        message = f"{what}: {describe(err)}"
    fail(message)  # outside the except block: no exception chain in the report
