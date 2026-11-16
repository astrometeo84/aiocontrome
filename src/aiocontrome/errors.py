"""Exceptions raised by aiocontrome."""

from __future__ import annotations

MAX_BODY_EXCERPT = 200
"""Maximum number of response body characters included in error messages.

Controme answers unknown routes with a ~240 kB Django debug page; never log it in full.
"""


class ContromeError(Exception):
    """Base class for all aiocontrome errors."""


class ContromeConnectionError(ContromeError):
    """The Controme Mini-Server could not be reached (network error or timeout)."""


class ContromeResponseError(ContromeError):
    """The server answered with an unexpected status, invalid JSON or an unexpected shape."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ContromeAuthError(ContromeResponseError):
    """Authentication failed or credentials are missing (HTTP 401/403)."""


class ContromeNotFoundError(ContromeResponseError):
    """The endpoint or object does not exist (HTTP 404)."""


class ContromeApiDisabledError(ContromeError):
    """The internal device API ``/api/v1/`` is disabled (``{"error": "api_disabled"}``)."""


def body_excerpt(body: str, limit: int = MAX_BODY_EXCERPT) -> str:
    """Return at most ``limit`` characters of ``body`` on a single line."""
    flat = " ".join(body.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "…"


def error_for_status(status: int, body: str = "") -> ContromeResponseError:
    """Map a non-2xx HTTP status to an exception; the body is truncated."""
    excerpt = body_excerpt(body)
    message = f"HTTP {status}" + (f": {excerpt}" if excerpt else "")
    if status in (401, 403):
        return ContromeAuthError(message, status=status)
    if status == 404:
        return ContromeNotFoundError(message, status=status)
    return ContromeResponseError(message, status=status)
