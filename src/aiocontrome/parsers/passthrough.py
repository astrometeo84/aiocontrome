"""Pass-through parser for endpoints without a known shape (``vtr/``, ``wetter_pro/``).

The recorded system returns ``{}`` for both, so no model can be derived yet. The payload is
handed out unchanged but immutable.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from ._common import expect_dict


def freeze(value: Any) -> Any:
    """Deep-convert dicts to read-only mappings and lists to tuples."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze(item) for item in value)
    return value


def parse_passthrough(data: Any, endpoint: str) -> Mapping[str, Any]:
    """Return the JSON object of ``endpoint`` deep-frozen; raise if it is no object."""
    frozen: Mapping[str, Any] = freeze(expect_dict(data, endpoint))
    return frozen
