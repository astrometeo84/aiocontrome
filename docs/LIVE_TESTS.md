# Live tests

An optional test suite that runs aiocontrome against a **real** Controme Mini-Server. It guards
against firmware changes and checks the assumptions recorded in the `controme-api` skill.

**Run it only from the maintainer's PC in the local network – never in CI, never in the dev
container.** The normal test run deselects these tests (`-m "not live"` in `pyproject.toml`),
and without configuration they are skipped.

## What is checked

All tests use `ContromeClient` with the time zone `Europe/Berlin`.

1. **Read and parse:** `info/`, `temps/`, `outs/`, `room_details/`, `upcomingoffsets/`, `fps/`,
   `vtr/`, `wetter_pro/` and `rltemps/<room>/` for the first room with return-flow sensors
   parse without error; the house has rooms; the room IDs of `temps/` and `room_details/` match.
2. **Guards for the observations of 2026-11-20** (a failure reads "Firmware-Verhalten
   geändert – Skill controme-api prüfen"):
   - `room_details/` returns data **without credentials** (Basic Auth is not checked).
     Until aiocontrome 0.3.0 the client refuses `room_details` without credentials, so this
     request is a plain GET without auth; it will use `get_room_details()` from 0.3.0 on.
   - `temps/` with house ID 99 returns the same room IDs as the configured house.
3. **Credential check** (only with username and password): `set_room_offset(99999, 0)` –
   room 99999 does not exist, offset 0 means "remove". Right credentials → 404, the same user
   with a random wrong password → 403.

## What the tests touch

Read endpoints only, plus the one credential probe above. That probe is a POST to a write
endpoint; it is presumably without effect (no before/after comparison has been made). No
other write call is made, nothing is changed on purpose.

## What the tests print

Only numbers, status codes, key names and counts. Never room or person names, sensor IDs,
MACs, the address or credentials, and no raw data. No files are written. Failures are
reported without traceback, because aiocontrome's exception texts contain the request URL.

## Running

On the maintainer's Windows PC, in the repository:

```powershell
.\scripts\run-live-tests.ps1
```

The script asks for the address (default: `$env:CONTROME_IP`), the username and the password
(entered as SecureString; leave the username or password empty to skip the credential check).
It sets the environment variables for this run only, starts

```text
uv run pytest -m live --no-cov -p no:cacheprovider -q --tb=short
```

and removes the variables again in a `finally` block. The password never appears in the
command line or the history; during the run it is visible to the pytest process through its
environment.

### Environment variables (for a manual run)

| Variable | Required | Meaning |
|---|---|---|
| `CONTROME_LIVE` | yes | must be `1`, otherwise all live tests are skipped |
| `CONTROME_HOST` | yes | address of the Mini-Server, e.g. `192.0.2.10` |
| `CONTROME_HOUSE` | no | house ID, default `1` |
| `CONTROME_USER`, `CONTROME_PASSWORD` | no | only for the credential check; without them it is skipped |

Prefer the script over setting `CONTROME_PASSWORD` by hand, so the password does not end up in
the shell history.
