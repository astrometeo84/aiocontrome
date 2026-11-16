# aiocontrome

Async Python client for the local HTTP API of **Controme Smart-Heat** (tested with NOVA 27).

> Status: early development – not yet published on PyPI.

- Documented read/write endpoints of the local JSON API (`get/json/v1`, `set/json/v1`)
- Parsing of known firmware quirks (output types relay vs. 0–10 V, sensor connection types,
  timestamp formats, …)
- No Home Assistant dependency – usable by any integration

## Usage

```python
from zoneinfo import ZoneInfo

import aiohttp
from aiocontrome import ContromeClient


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        client = ContromeClient(
            session,
            "192.0.2.10",  # Mini-Server address
            timezone=ZoneInfo("Europe/Berlin"),  # required: Controme reports local time
            username="…",  # only needed for get_room_details() and set_… methods
            password="…",
        )
        house = await client.get_house()  # house ID is detected on first use
        for room in house.rooms:
            print(room.name, room.temperature, room.setpoint)
        for output in await client.get_outputs():
            print(output.key, output.type, output.percent)
```

### Writing

```python
from aiocontrome import DEFAULT_DURATION, OperatingMode

await client.set_setpoint(3, 21.5)  # permanent setpoint
await client.set_target(3, 19.0, duration=90)  # temporary, 90 minutes
await client.set_scene(4, room_id=3, duration=DEFAULT_DURATION)  # without room_id: all rooms
await client.set_operating_mode(OperatingMode.OFF, room_id=3)
await client.set_room_offset(3, -1.0, name="my_integration")  # expires after 10 min
```

Write calls send the credentials as form fields over plain HTTP (the Mini-Server has no TLS):
use them only in the local network. Values are **not range-checked** – the API documents no
limits, so plausibility checks are up to the caller. `set_house_offset` is not documented in
detail; its fields are assumed to match `set_room_offset`.

Errors derive from `ContromeError` (`ContromeConnectionError`, `ContromeAuthError`,
`ContromeNotFoundError`, `ContromeResponseError`, …).

Not affiliated with Controme GmbH. License: GPL-3.0.
