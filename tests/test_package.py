"""Package metadata."""

from __future__ import annotations

import tomllib
from pathlib import Path

import aiocontrome

ROOT = Path(__file__).parent.parent


def test_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert aiocontrome.__version__ == project["version"]


def test_changelog_has_entry_for_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{aiocontrome.__version__}] - " in changelog
