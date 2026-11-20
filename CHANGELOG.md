# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-11-20

Live-verified against a NOVA 27 Mini-Server (one-house system): the live suite passed
(`get_room_details()` without credentials, `verify_credentials()` 404/403).

### Added

- Optional live test suite (`tests/live/`, marker `live`) against a real Mini-Server: reads and
  parses the read endpoints the client supports (`info/`, `temps/`, `outs/`, `room_details/`,
  `upcomingoffsets/`, `fps/`, `vtr/`, `wetter_pro/`, `rltemps/` for one room), guards the
  observations of 2026-11-20 (`room_details/` without credentials, unknown house ID on a
  one-house system) and checks credentials via `verify_credentials()`.
  Configured only through `CONTROME_*` environment variables; deselected in normal runs and CI
  (`-m "not live"`). Run it with `scripts/run-live-tests.ps1`; see `docs/LIVE_TESTS.md`.
- `ContromeClient.verify_credentials()`: checks username and password with a POST to
  `roomoffset/99999/` (room does not exist, `offset=0.00`, `offset_name=insights_probe`), the
  values tested live on 2026-11-20. 404 with an empty body → valid, 403 → `ContromeAuthError`,
  any other answer → `ContromeResponseError` ("credentials could not be verified"), no request
  without credentials.
- `basic_auth_header` is exported from `aiocontrome`.
- `tzdata` in the `dev` extra, so the tests find `Europe/Berlin` on Windows (no IANA database
  there). Not a runtime dependency: callers pass the time zone themselves.

### Changed

- **No Basic Auth on read calls.** `get_room_details()` and `get_raw("room_details")` send no
  credentials and need none (`room_details/` does not check them, live test 2026-11-20).
  Without credentials they **no longer raise `ContromeAuthError`** before sending; they return
  the data. If `room_details/` answers 401/403 and credentials are configured, the request is
  retried once with Basic Auth (fallback for other firmware); a second 401/403 raises
  `ContromeAuthError`, as does a 401/403 without credentials.

### Fixed

- `scripts/run-live-tests.ps1` runs `uv run --extra dev pytest`, so the test tools are installed
  on the first run instead of failing with "Failed to spawn: pytest".

## [0.2.0] - 2026-11-19

### Added

- Room and sensor classification: `Room.is_controlled` (room has a room temperature sensor),
  `Room.return_sensors` (all other sensors except 1-Wire humidity; matches `rltemps/`),
  `Room.system_sensors` and `House.system_sensors` (sensors of rooms without control).

### Security

- Error messages no longer leak credentials in other forms: the password is removed raw,
  HTML-escaped and URL-encoded, the Basic Auth token with and without `Basic `, and the
  username as a whole word. All are replaced by `**REDACTED**` (previously `***`).
- The body excerpt in the "Invalid JSON" error is redacted as well.
- `redact()` also redacts the keys `authorization`, `cookie`, `sessionid`, `csrftoken` and
  `csrfmiddlewaretoken` (case-insensitive).

## [0.1.0] - 2026-11-17

First public release. Tested against fixtures recorded from a Controme Smart-Heat NOVA 27
system; the write endpoints `set_setpoint`, `set_target`, `set_room_offset` and
`set_house_offset` (with 0) were verified in a live test.

### Added

- `ContromeClient` for the local JSON API (`get/json/v1`), with the session passed in, a
  required `timezone` and automatic detection of the house ID.
- Read methods returning immutable, typed models: `get_info`, `get_house` (`temps/`),
  `get_outputs` (`outs/`), `get_return_sensors` (`rltemps/`), `get_room_details` (Basic Auth),
  `get_upcoming_offsets` and `get_fps`.
- Write methods (`set/json/v1`): `set_setpoint`, `set_target`, `set_scene`,
  `set_default_duration`, `set_operating_mode`, `set_room_offset` and `set_house_offset`.
  Credentials are never logged or included in errors.
- Output type per floor (relay or 0-10 V position) with automatic detection, plus
  `Output.percent` and `Output.open_fraction`.
- Sensor connection type derived from the sensor ID (1-Wire, radio, virtual),
  `LastSeenTracker` and `is_stale` for transmission monitoring.
- Window-open detection (`RoomDetails.window_open`) and per-source offsets, including the API
  offset in `offsets["api"]`.
- `get_raw` for unparsed responses, `get_vtr` and `get_weather_pro` as read-only pass-through,
  and `redact` to remove sensor IDs, MAC and IP addresses from data before sharing it.
- Error hierarchy based on `ContromeError` (`ContromeConnectionError`, `ContromeAuthError`,
  `ContromeNotFoundError`, `ContromeResponseError`, `ContromeApiDisabledError`).

[Unreleased]: https://github.com/astrometeo84/aiocontrome/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/astrometeo84/aiocontrome/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/astrometeo84/aiocontrome/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/astrometeo84/aiocontrome/releases/tag/v0.1.0
