# Live tests

An optional test suite that runs aiocontrome against a **real** Controme Mini-Server. It guards
against firmware changes and re-checks some of the observations recorded in the `controme-api`
skill (not its open assumptions, such as `roomoffsets/` with an active offset or the untested
write calls).

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
   - `room_details/` returns data **without credentials** (Basic Auth is not checked):
     `get_room_details()` on a client without credentials.
   - `temps/` with house ID 99 returns the same room IDs as house 1. Observed on a one-house
     system; skipped when `CONTROME_HOUSE` is not 1 (multi-house behaviour is unknown).
3. **Credential check** (only with username and password): `verify_credentials()`, a POST to
   `roomoffset/99999/` (room does not exist, offset 0). Right credentials pass (404 with an
   empty body; an unknown route would answer 404 with the Django debug page), the same user
   with a random wrong password → `ContromeAuthError` 403. One failed login per run; no
   lockout has been observed so far.

## What the tests touch

Read endpoints only, plus the one credential probe above. That probe is a POST to a write
endpoint; no effect has been observed (a before/after comparison of `room_details/` around a
run on 2026-11-20 showed only measurement changes, no change under offsets). No other write
call is made, nothing is changed on purpose.

## What the tests print

Only numbers, status codes, key names and counts. Never room or person names, sensor IDs,
MACs, the address or credentials, and no raw data. Failures are reported without exception
text, because aiocontrome's exception texts contain the request URL. When `CONTROME_LIVE=1` is
set, the suite forces short tracebacks without local variables (`--tb=short`, no
`--showlocals`), and host and credentials are left out of the `repr` of its fixtures.
Do not add `--log-level=DEBUG`: aiocontrome logs request URLs (with the address) at DEBUG.

The tests write no files of their own. The script disables the coverage data and the pytest
cache; Python may still write `__pycache__` byte code as in any test run.

## First run on Windows

The script needs [uv](https://docs.astral.sh/uv/) on the `PATH`; nothing else has to be set up
by hand, as long as uv finds Python 3.13 or newer or may download it (its default). On the first run `uv run --extra dev` creates the virtual environment and installs the
test tools from `uv.lock` (including `tzdata`, because Windows has no IANA time zone database
for `Europe/Berlin`). This takes a while; later runs start right away.

## Running

On the maintainer's Windows PC, in the repository:

```powershell
.\scripts\run-live-tests.ps1
```

The script asks for the address (default: `$env:CONTROME_IP`), the username and the password
(entered as SecureString; leave the username or password empty to skip the credential check).
It sets the environment variables for this run only, starts

```text
uv run --extra dev pytest -m live --no-cov -p no:cacheprovider -q --tb=short
```

and restores the previous environment in a `finally` block: `CONTROME_*` variables left over in
the session are cleared for the run (so an old password or house ID cannot be used by
accident) and restored afterwards. The script always tests house 1; for another house use a
manual run. The password never appears in the command line or the history; during the run it
is visible to the pytest process through its environment.

### Environment variables (for a manual run)

| Variable | Required | Meaning |
|---|---|---|
| `CONTROME_LIVE` | yes | must be `1`, otherwise all live tests are skipped |
| `CONTROME_HOST` | yes | address of the Mini-Server, e.g. `192.0.2.10` |
| `CONTROME_HOUSE` | no | house ID, default `1` |
| `CONTROME_USER`, `CONTROME_PASSWORD` | no | only for the credential check; without them it is skipped |

For a manual run use the same options as the script, so no coverage data or cache is written:

```text
uv run --extra dev pytest -m live --no-cov -p no:cacheprovider -q --tb=short
```

Prefer the script over setting `CONTROME_PASSWORD` by hand, so the password does not end up in
the shell history.
