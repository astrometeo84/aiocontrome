# aiocontrome – Projektregeln für Claude Code

Async-Python-Client für die lokale HTTP-API von Controme Smart-Heat (NOVA 27).
Wird genutzt von der HA-Integration `ha-controme-insights` und soll auch für andere Integrationen
(z. B. flame4ever/homeassistant-controme-integration) nutzbar sein. Lizenz: GPL-3.0.

## Sprache
- Mit dem Nutzer: **Deutsch**.
- Code, Kommentare, Docstrings, README, Commit-Nachrichten, PR-Texte: **Englisch**.

## Sicherheitsregeln (nicht verhandelbar)
1. **Niemals eine echte Controme-Anlage oder Geräte im Heimnetz ansprechen.** Der Container hat
   absichtlich keinen Weg ins Heimnetz. Entwickelt und getestet wird nur gegen `tests/fixtures/`
   und gemocktes HTTP über einen lokalen aiohttp-Testserver auf 127.0.0.1 (Fixture
   `controme_server` in `tests/conftest.py`) statt `aioresponses`. Fehlen Daten, den Nutzer
   bitten, sie zu besorgen.
2. **Keine Zugangsdaten** anlegen, erfragen oder speichern. Keine `.env` mit Passwörtern.
3. **Keine echten Kennungen ins Repo**: Raum-/Personennamen, MACs, Fühler-IDs, IPs nur pseudonymisiert
   (siehe Skill `controme-api`, Abschnitt Pseudonymization).
4. **GitHub:** nur auf Feature-Branches arbeiten (`feat/…`, `fix/…`, `chore/…`), Pushes nur nach
   Rückfrage, PRs mit `ghb pr create`. Nie direkt nach `main`, nie Force-Push, nie Tags, nie Releases.
5. **`.github/workflows/` nicht ändern** (die GitHub App darf das nicht). Änderungsvorschläge als Text
   an den Nutzer.
6. **Neue Abhängigkeiten nur nach Rückfrage.** Laufzeit: nur `aiohttp`.

## Architektur
```
src/aiocontrome/
  client.py      ContromeClient(session, host, *, house_id=None, username=None, password=None)
                 – async Methoden je Endpunkt, liefert Modelle; Schreib-Methoden separat (set_…)
  models.py      dataclasses (frozen, slots): House, Floor, Room, Sensor, Output, RoomDetails, Fps …
  parsers/       ein Modul je Endpunkt, reine Funktionen dict → Modell (ohne I/O, gut testbar)
  outputs.py     Ausgangstyp (relay / position) inkl. Auto-Erkennung je Etage
  sensors.py     Erkennung der Anbindung aus der Fühler-ID; Zeitstempel-Parsing; Veraltung
  errors.py      ContromeError, ContromeConnectionError, ContromeAuthError, ContromeApiDisabledError …
  redact.py      Schwärzung von Rohdaten (Fühler-IDs, MACs, IPs) für Diagnose-Downloads
```
- Kein Home-Assistant-Import, keine globale Session: Session wird übergeben.
- Zeitstempel als `datetime` mit Zeitzone; Controme liefert lokale Zeit → Zeitzone als Parameter.
- Alle Eigenheiten der API stehen im Skill `controme-api`. **Jede** dort genannte Eigenheit braucht
  einen Test.

## Qualität
- Typisiert, `mypy --strict` sauber; `ruff` (Lint + Format).
- Tests mit `pytest`, `pytest-asyncio` und dem lokalen aiohttp-Testserver (`aiohttp.test_utils`,
  Fixture `controme_server`); kein `aioresponses` (inkompatibel mit aiohttp ≥ 3.14). Ziel ≥ 90 % Abdeckung.
- Kleine PRs, je Thema einer. Jede Funktion mit Tests aus den Fixtures.

## Befehle
```bash
uv sync --all-extras          # Abhängigkeiten
uv run pytest                 # Tests
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

## Arbeitsweise
- Vor größeren Schritten einen kurzen Plan zeigen und auf Freigabe warten.
- Unklarheiten zur API: erst Fixtures und Skill prüfen, dann den Nutzer fragen – nicht raten.
- Schreib-Endpunkte (`set/json/v1/…`): Parameter aus der offiziellen Doku, Tests nur gegen den lokalen Testserver.
  Live-Tests macht ausschließlich der Nutzer.
