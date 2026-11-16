from __future__ import annotations

import pytest

from aiocontrome.errors import (
    MAX_BODY_EXCERPT,
    ContromeAuthError,
    ContromeError,
    ContromeNotFoundError,
    ContromeResponseError,
    body_excerpt,
    error_for_status,
)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_statuses_map_to_auth_error(status: int) -> None:
    err = error_for_status(status, "Unauthorized")
    assert type(err) is ContromeAuthError
    assert err.status == status
    assert isinstance(err, ContromeError)


def test_404_maps_to_not_found_and_truncates_debug_page() -> None:
    # Controme answers unknown routes with a ~240 kB Django debug page.
    body = "<!DOCTYPE html>\n<html>\n" + "<li>route</li>\n" * 20_000
    err = error_for_status(404, body)
    assert type(err) is ContromeNotFoundError
    message = str(err)
    assert message.startswith("HTTP 404: <!DOCTYPE html> <html>")
    assert len(message) <= len("HTTP 404: ") + MAX_BODY_EXCERPT + 1
    assert "\n" not in message


def test_other_status_maps_to_response_error_without_body() -> None:
    err = error_for_status(500)
    assert type(err) is ContromeResponseError
    assert str(err) == "HTTP 500"
    assert err.status == 500


def test_body_excerpt_keeps_short_bodies() -> None:
    assert body_excerpt("  short\n body ") == "short body"
    assert body_excerpt("x" * 10, limit=5) == "xxxxx…"
