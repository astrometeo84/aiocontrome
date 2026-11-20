"""Shared test helpers.

HTTP tests run against a local aiohttp test server on 127.0.0.1 (``controme_server``) that
serves the recorded fixtures. Never point tests at a real Controme system.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import re
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

# pytester (built into pytest, no network): runs pytest in-process on generated files; used to
# prove that live-test reports never show host or password (tests/live/test_config.py).
pytest_plugins = ["pytester"]

FIXTURES = Path(__file__).parent / "fixtures"

# Obviously fake credentials, so a search for them in errors and logs is unambiguous.
TEST_USER = "user-test"
TEST_PASSWORD = "pw-test-SECRET"
TEST_PASSWORD_SPECIAL = "pw&test+SECRET%"
"""Changes under HTML escaping and URL encoding."""


def secret_forms(username: str, password: str) -> list[str]:
    """Every form of the credentials that must never appear in errors or logs.

    The username is left out: it is redacted only as a whole word, so test it separately.
    """
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return [
        password,
        html.escape(password),
        quote(password),
        quote_plus(password),
        token,
        f"Basic {token}",
    ]


def echo_page(username: str, password: str) -> str:
    """An error page echoing the credentials in every form, like a Django debug page."""
    return (
        "<html><body><h1>Server Error</h1><pre>"
        f"user={username} password={password} "
        f"html={html.escape(password)} quote={quote(password)} plus={quote_plus(password)} "
        f"HTTP_AUTHORIZATION: {secret_forms(username, password)[-1]}"
        "</pre></body></html>"
    )


def assert_no_secrets(text: str, username: str, password: str) -> None:
    """Assert that ``text`` contains neither the password (in any form) nor the token."""
    for form in secret_forms(username, password):
        assert form not in text, f"{form!r} leaked"
    assert re.search(rf"(?<!\w){re.escape(username)}(?!\w)", text) is None, "username leaked"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture from ``tests/fixtures``."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_text_fixture(name: str) -> str:
    """Load a non-JSON fixture (e.g. an HTML error page) from ``tests/fixtures``."""
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def temps() -> Any:
    return load_fixture("temps.json")


def iter_sensors(data: Any) -> list[dict[str, Any]]:
    """All raw sensors of a ``temps/`` response."""
    return [s for floor in data for room in floor["raeume"] for s in room["sensoren"]]


def iter_outputs(data: Any) -> list[tuple[int, int, str, float]]:
    """All raw outputs of an ``outs/`` response as ``(floor, room, key, value)``."""
    return [
        (floor["id"], room["id"], key, value)
        for floor in data
        for room in floor["raeume"]
        for key, value in room["ausgang"].items()
    ]


# --- local fake Controme server ---------------------------------------------------------


def api_path(endpoint: str, house_id: int = 1) -> str:
    """Request path of a read endpoint, e.g. ``/get/json/v1/1/temps/``."""
    return f"/get/json/v1/{house_id}/{endpoint}/"


def set_path(endpoint: str, house_id: int = 1) -> str:
    """Request path of a write endpoint, e.g. ``/set/json/v1/1/soll/3/``."""
    return f"/set/json/v1/{house_id}/{endpoint}/"


_NO_PAYLOAD = object()


@dataclass(frozen=True)
class FakeResponse:
    """One canned response of the fake server."""

    status: int = 200
    payload: Any = _NO_PAYLOAD
    """JSON-serialisable body; ignored if ``body`` is set."""
    body: str | None = None
    """Raw body, e.g. broken JSON or an HTML error page."""
    content_type: str = "application/json"
    delay: float = 0.0
    """Seconds to wait before answering (simulates a timeout)."""


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    path: str
    query: str
    authorization: str | None
    content_type: str = ""
    form: dict[str, str] = field(default_factory=dict)
    """Decoded form fields of a POST request."""


@dataclass
class FakeControme:
    """Fake Mini-Server: canned responses per path, records every request.

    Responses registered for the same path are served in order; the last one repeats.
    Unknown paths answer with the synthetic Django 404 debug page, like the real server.
    """

    host: str = ""
    requests: list[RecordedRequest] = field(default_factory=list)
    _routes: dict[str, list[FakeResponse]] = field(default_factory=dict)

    def add(
        self,
        path: str,
        payload: Any = _NO_PAYLOAD,
        *,
        status: int = 200,
        body: str | None = None,
        content_type: str | None = None,
        delay: float = 0.0,
    ) -> None:
        """Register a response for ``path`` (see ``api_path``)."""
        if content_type is None:
            content_type = "application/json" if body is None else "text/html"
        self._routes.setdefault(path, []).append(
            FakeResponse(status, payload, body, content_type, delay)
        )

    def add_fixture(self, path: str, fixture: str) -> None:
        """Serve a JSON fixture file at ``path``."""
        self.add(path, load_fixture(fixture))

    def add_auth_error(self, path: str, status: int = 401) -> None:
        self.add(path, status=status, body="", content_type="text/plain")

    def add_not_found(self, path: str, *, pad_to: int = 0) -> None:
        """Serve the synthetic Django 404 page, optionally padded to ``pad_to`` characters."""
        page = load_text_fixture("synthetic_404_debug.html")
        if pad_to > len(page):
            filler = "<li>padding</li>\n"
            page = page.replace("</ol>", filler * (pad_to // len(filler) + 1) + "</ol>")
        self.add(path, status=404, body=page)

    def add_broken_json(self, path: str, body: str = "<html>not json</html>") -> None:
        self.add(path, body=body, content_type="text/html")

    def add_timeout(self, path: str, delay: float = 0.5) -> None:
        """Answer only after ``delay`` seconds; use a shorter client timeout."""
        self.add(path, [], delay=delay)

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [r for r in self.requests if r.path == path]

    def add_recorded(self, path: str, fixture: str) -> None:
        """Replay a recorded raw HTTP response (``curl -i`` output, e.g. ``write/soll_ok.txt``)."""
        raw = load_text_fixture(fixture).replace("\r\n", "\n")
        head, _, body = raw.partition("\n\n")
        status_line, *header_lines = head.split("\n")
        headers = dict(line.split(": ", 1) for line in header_lines if ": " in line)
        content_type = headers.get("Content-Type", "text/plain").split(";")[0].strip()
        self.add(
            path, status=int(status_line.split()[1]), body=body.strip(), content_type=content_type
        )

    def add_ok(self, path: str, body: str = "") -> None:
        """Answer a write request with HTTP 200 (the real success body is not yet known)."""
        self.add(path, body=body, content_type="text/plain")

    async def handle(self, request: web.Request) -> web.StreamResponse:
        form = {str(k): str(v) for k, v in (await request.post()).items()}
        self.requests.append(
            RecordedRequest(
                request.method,
                request.path,
                request.query_string,
                request.headers.get("Authorization"),
                request.content_type,
                form,
            )
        )
        queue = self._routes.get(request.path)
        if not queue:
            page = load_text_fixture("synthetic_404_debug.html")
            return web.Response(status=404, text=page, content_type="text/html")
        response = queue.pop(0) if len(queue) > 1 else queue[0]
        if response.delay:
            await asyncio.sleep(response.delay)
        text = response.body if response.body is not None else json.dumps(response.payload)
        return web.Response(status=response.status, text=text, content_type=response.content_type)


@pytest.fixture
async def controme_server() -> AsyncIterator[FakeControme]:
    """A running fake Controme Mini-Server on 127.0.0.1."""
    fake = FakeControme()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    fake.host = f"127.0.0.1:{server.port}"
    try:
        yield fake
    finally:
        await server.close()


@pytest.fixture
def unused_host() -> str:
    """``127.0.0.1:<port>`` where nothing listens (connection refused)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"127.0.0.1:{port}"
