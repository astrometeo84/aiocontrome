"""Redaction of raw API data, e.g. for a diagnostics download.

Controme responses contain identifiers that must not be shared: 1-Wire sensor IDs, MAC
addresses of radio devices and, in error pages or configuration, IP addresses. Room names and
sensor descriptions are kept because they are needed to understand a problem.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .sensors import detect_connection

REDACTED = "**REDACTED**"

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"password", "passwort", "user", "username", "benutzer", "host", "ip", "mac", "token"}
)
"""Keys (case-insensitive) whose values are replaced by ``REDACTED``."""

_HEX = "[0-9a-f]{2}"
_SENSOR_ID = re.compile(
    rf"(?<![0-9a-z_:])"
    rf"(?:{_HEX}(?:_{_HEX}){{7}}|{_HEX}(?::{_HEX}){{5}}|{_HEX}(?::{_HEX}){{3}})"
    rf"(?![0-9a-z_:])",
    re.IGNORECASE,
)
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def redact(data: Any, *, keys: Iterable[str] = SENSITIVE_KEYS) -> Any:
    """Return a redacted deep copy of decoded JSON; ``data`` itself is not changed.

    - Sensor IDs (any 8-byte 1-Wire-style ID ``xx_xx_xx_xx_xx_xx_xx_xx``) and MAC addresses
      (6 or 4 bytes) become stable placeholders named after the connection type, e.g.
      ``**onewire_temperature_1**``, whether they appear as values, dict keys or inside text.
      The same ID always gets the same placeholder within one call, so pass all responses
      together (e.g. a dict of endpoint → response) to keep references between them
      recognisable.
    - IPv4 addresses inside text become ``REDACTED``.
    - Values of ``keys`` (compared case-insensitively) become ``REDACTED``; ``None`` stays.

    Lists and tuples come back as lists, mappings as dicts.
    """
    return _Redactor(keys).value(data)


class _Redactor:
    def __init__(self, keys: Iterable[str]) -> None:
        self._keys = frozenset(key.casefold() for key in keys)
        self._placeholders: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def value(self, data: Any) -> Any:
        if isinstance(data, Mapping):
            return {
                self.text(str(key)): (
                    REDACTED
                    if str(key).casefold() in self._keys and item is not None
                    else self.value(item)
                )
                for key, item in data.items()
            }
        if isinstance(data, list | tuple):
            return [self.value(item) for item in data]
        if isinstance(data, str):
            return self.text(data)
        return data

    def text(self, text: str) -> str:
        text = _SENSOR_ID.sub(lambda match: self._placeholder(match.group()), text)
        return _IPV4.sub(REDACTED, text)

    def _placeholder(self, sensor_id: str) -> str:
        key = sensor_id.casefold()
        if key not in self._placeholders:
            kind = detect_connection(sensor_id).value
            self._counters[kind] = self._counters.get(kind, 0) + 1
            self._placeholders[key] = f"**{kind}_{self._counters[kind]}**"
        return self._placeholders[key]
