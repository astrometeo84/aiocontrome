"""Offline tests of the live-test configuration (no marker: they run in every normal run)."""

from __future__ import annotations

import pytest

from .conftest import Credentials, LiveConfig, _read_config

HOST = "192.0.2.10"
PASSWORD = "pw-test-SECRET"
ENV = ("CONTROME_LIVE", "CONTROME_HOST", "CONTROME_HOUSE", "CONTROME_USER", "CONTROME_PASSWORD")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


def test_repr_hides_host_and_credentials() -> None:
    # pytest prints fixture arguments of failing tests with repr().
    text = repr(LiveConfig(host=HOST, house_id=1, username="user-test", password=PASSWORD))
    text += repr(Credentials("user-test", PASSWORD))
    assert HOST not in text
    assert "user-test" not in text
    assert PASSWORD not in text


@pytest.mark.parametrize(
    ("env", "reason"),
    [
        ({}, "CONTROME_LIVE=1 not set"),
        ({"CONTROME_LIVE": "true", "CONTROME_HOST": HOST}, "CONTROME_LIVE=1 not set"),
        ({"CONTROME_LIVE": "1"}, "CONTROME_HOST not set"),
        ({"CONTROME_LIVE": "1", "CONTROME_HOST": "  "}, "CONTROME_HOST not set"),
        ({"CONTROME_LIVE": "1", "CONTROME_HOST": HOST, "CONTROME_HOUSE": "0"}, "positive integer"),
        ({"CONTROME_LIVE": "1", "CONTROME_HOST": HOST, "CONTROME_HOUSE": "x"}, "positive integer"),
    ],
)
def test_skip_reasons(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], reason: str) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    result = _read_config()
    assert isinstance(result, str)
    assert reason in result
    assert HOST not in result


def test_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROME_LIVE", "1")
    monkeypatch.setenv("CONTROME_HOST", f" {HOST} ")
    monkeypatch.setenv("CONTROME_HOUSE", "2")
    config = _read_config()
    assert isinstance(config, LiveConfig)
    assert (config.host, config.house_id, config.has_credentials) == (HOST, 2, False)
    monkeypatch.setenv("CONTROME_USER", "user-test")
    monkeypatch.setenv("CONTROME_PASSWORD", PASSWORD)
    config = _read_config()
    assert isinstance(config, LiveConfig)
    assert config.has_credentials
