"""Sensor helpers: connection type, values, timestamps and staleness."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta, tzinfo
from types import MappingProxyType

from .models import SensorConnection

_HEX = "[0-9a-f]{2}"
_CONNECTION_PATTERNS: tuple[tuple[re.Pattern[str], SensorConnection], ...] = (
    (re.compile(rf"^12_00_00_00_00_00_00_{_HEX}$", re.I), SensorConnection.VIRTUAL),
    (re.compile(rf"^28(?:_{_HEX}){{7}}$", re.I), SensorConnection.ONEWIRE_TEMPERATURE),
    (re.compile(rf"^26(?:_{_HEX}){{7}}$", re.I), SensorConnection.ONEWIRE_HUMIDITY),
    (re.compile(rf"^{_HEX}(?::{_HEX}){{5}}$", re.I), SensorConnection.RADIO_ROOM_CONTROLLER),
    (re.compile(rf"^{_HEX}(?::{_HEX}){{3}}$", re.I), SensorConnection.RADIO_SENSOR),
)

TEMPS_TIME_FORMAT = "%d.%m.%Y %H:%M"
"""``letzte_uebertragung`` in ``temps/``."""
RLTEMPS_TIME_FORMAT = "%H:%M:%S %d.%m.%Y"
"""``letzte_uebertragung`` in ``rltemps/``."""

MULTI_SENSOR_TEMPERATURE_KEY = "Temperatur"


def detect_connection(sensor_id: str) -> SensorConnection:
    """Derive the connection type from a sensor ID."""
    sensor_id = sensor_id.strip()
    for pattern, connection in _CONNECTION_PATTERNS:
        if pattern.match(sensor_id):
            return connection
    return SensorConnection.UNKNOWN


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def split_sensor_value(raw: object) -> tuple[float | None, Mapping[str, float]]:
    """Split a raw ``wert`` into ``(value, readings)``.

    A number yields ``(number, {})``. A dict (radio multi-sensor) yields its non-null numeric
    entries as readings; the value is ``readings["Temperatur"]`` if present. Anything else
    yields ``(None, {})``.
    """
    if isinstance(raw, Mapping):
        readings = {
            str(key): number
            for key, item in raw.items()
            if (number := _as_number(item)) is not None
        }
        return readings.get(MULTI_SENSOR_TEMPERATURE_KEY), MappingProxyType(readings)
    return _as_number(raw), MappingProxyType({})


def parse_local_time(value: object, fmt: str, tz: tzinfo) -> datetime | None:
    """Parse a local time string with ``fmt`` in ``tz``. Non-string/empty/invalid → ``None``."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), fmt).replace(tzinfo=tz)
    except ValueError:
        return None


def parse_temps_time(value: str | None, tz: tzinfo) -> datetime | None:
    """Parse ``"dd.mm.yyyy HH:MM"`` (local time). ``None``/empty/invalid → ``None``."""
    return parse_local_time(value, TEMPS_TIME_FORMAT, tz)


def parse_rltemps_time(value: str | None, tz: tzinfo) -> datetime | None:
    """Parse ``"HH:MM:SS dd.mm.yyyy"`` (local time). ``None``/empty/invalid → ``None``."""
    return parse_local_time(value, RLTEMPS_TIME_FORMAT, tz)


def is_stale(last: datetime | None, now: datetime, max_age: timedelta) -> bool:
    """``True`` if ``last`` is unknown or older than ``max_age``."""
    return last is None or now - last > max_age


class LastSeenTracker:
    """Remember the last transmission time per sensor.

    Controme reports ``null`` when there is no current value, which does not mean the sensor
    never transmitted. Feed every poll into ``update`` to keep the last known time.
    """

    def __init__(self) -> None:
        self._last_seen: dict[str, datetime] = {}

    def update(self, sensor_id: str, last_transmission: datetime | None) -> datetime | None:
        """Record a reported time (``None`` keeps the previous one) and return the last known."""
        if last_transmission is not None:
            previous = self._last_seen.get(sensor_id)
            if previous is None or last_transmission > previous:
                self._last_seen[sensor_id] = last_transmission
        return self._last_seen.get(sensor_id)

    def get(self, sensor_id: str) -> datetime | None:
        """Return the last known transmission time of a sensor."""
        return self._last_seen.get(sensor_id)
