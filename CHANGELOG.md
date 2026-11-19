# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/astrometeo84/aiocontrome/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/astrometeo84/aiocontrome/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/astrometeo84/aiocontrome/releases/tag/v0.1.0
