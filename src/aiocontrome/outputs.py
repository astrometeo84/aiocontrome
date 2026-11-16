"""Output type handling (relay vs. valve position) per floor."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import Output, OutputType


class OutputTypeDetector:
    """Determine the output type per floor.

    Relay gateways only report 0/1, FBH-Gateway PRO reports 0-100. A single value cannot tell
    them apart (1 may mean 1 %), so a floor counts as ``POSITION`` once any value > 1 was seen.
    Configured types take precedence over detection. Assumes one gateway type per floor.
    """

    def __init__(self, configured: Mapping[int, OutputType] | None = None) -> None:
        self._configured = {
            floor_id: kind
            for floor_id, kind in (configured or {}).items()
            if kind is not OutputType.UNKNOWN
        }
        self._position_floors: set[int] = set()

    def observe(self, floor_id: int, value: float) -> None:
        """Record a raw output value of a floor."""
        if value > 1:
            self._position_floors.add(floor_id)

    def observe_outputs(self, outputs: Iterable[Output]) -> None:
        """Record the raw values of several outputs."""
        for output in outputs:
            self.observe(output.floor_id, output.raw_value)

    def type_for(self, floor_id: int) -> OutputType:
        """Return the configured or detected type of a floor."""
        if floor_id in self._configured:
            return self._configured[floor_id]
        if floor_id in self._position_floors:
            return OutputType.POSITION
        return OutputType.UNKNOWN
