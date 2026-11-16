"""Shared helpers for the response parsers (pure functions, no I/O)."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from datetime import datetime, tzinfo
from types import MappingProxyType
from typing import Any

from ..errors import ContromeApiDisabledError, ContromeError, ContromeResponseError
from ..models import Offset

LOCAL_MINUTE_FORMAT = "%Y-%m-%d %H:%M"
"""``next_due_time`` / ``nextDueTime`` and similar fields (local time)."""


def wrap_shape_errors[**P, R](endpoint: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Turn ``KeyError``/``TypeError``/``ValueError``/``AttributeError`` into a response error.

    Parsers access required fields directly; any structural surprise surfaces as
    ``ContromeResponseError`` naming the endpoint instead of a bare Python exception.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return func(*args, **kwargs)
            except ContromeError:
                raise
            except (KeyError, TypeError, ValueError, AttributeError) as err:
                raise ContromeResponseError(
                    f"Unexpected {endpoint} response: {type(err).__name__}: {err}"
                ) from err

        return wrapper

    return decorator


def check_api_error(data: Any) -> None:
    """Raise if ``data`` is an error object (``{"error": …}``) instead of a payload."""
    if isinstance(data, Mapping) and isinstance(data.get("error"), str):
        if data["error"] == "api_disabled":
            raise ContromeApiDisabledError("The device API /api/v1/ is disabled")
        raise ContromeResponseError(f"Controme returned error {data['error']!r}")


def expect_list(data: Any, endpoint: str) -> list[Any]:
    """Return ``data`` if it is a list, else raise ``ContromeResponseError``."""
    check_api_error(data)
    if not isinstance(data, list):
        raise ContromeResponseError(f"Unexpected {endpoint} response: expected a list")
    return data


def expect_dict(data: Any, endpoint: str) -> Mapping[str, Any]:
    """Return ``data`` if it is a dict, else raise ``ContromeResponseError``."""
    check_api_error(data)
    if not isinstance(data, Mapping):
        raise ContromeResponseError(f"Unexpected {endpoint} response: expected an object")
    return data


def to_float(value: Any) -> float | None:
    """Number or numeric string → ``float``; anything else (incl. ``bool``) → ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def req_float(value: Any, name: str) -> float:
    """Like ``to_float`` but the value is required."""
    number = to_float(value)
    if number is None:
        raise ValueError(f"{name} is not a number: {value!r}")
    return number


def to_int(value: Any) -> int | None:
    """Integer (or integral number/string) → ``int``; anything else → ``None``."""
    number = to_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def req_int(value: Any, name: str) -> int:
    """Like ``to_int`` but the value is required."""
    number = to_int(value)
    if number is None:
        raise ValueError(f"{name} is not an integer: {value!r}")
    return number


def to_str(value: Any) -> str | None:
    """Non-empty string → itself; ``None``/empty → ``None``; others → ``str(value)``."""
    if value is None:
        return None
    text = str(value)
    return text or None


def parse_iso(value: Any, tz: tzinfo) -> datetime | None:
    """Parse ISO 8601; naive values are local time in ``tz``. Invalid → ``None``."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=tz)


def parse_offsets(raw: Any) -> Mapping[str, Offset]:
    """``{source: {"raum": x, "haus": y}}`` → ``{source: Offset}``.

    Sources without values (e.g. ``"api": {}``) are omitted.
    """
    offsets: dict[str, Offset] = {}
    if isinstance(raw, Mapping):
        for source, item in raw.items():
            if not isinstance(item, Mapping):
                continue
            room, house = to_float(item.get("raum")), to_float(item.get("haus"))
            if room is None and house is None:
                continue
            offsets[str(source)] = Offset(room=room or 0.0, house=house or 0.0)
    return MappingProxyType(offsets)
