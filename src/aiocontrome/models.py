"""Data models returned by aiocontrome.

All models are immutable. Timestamps are timezone-aware ``datetime`` objects; Controme reports
local time, which the parsers convert using the time zone passed to the client.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

_EMPTY: Mapping[str, float] = MappingProxyType({})

WINDOW_OPEN_OFFSET_SOURCE = "Fenster-offen-Erkennung"
"""Offset source that becomes negative (seen: -10 K) while a window is open."""


class SensorConnection(StrEnum):
    """How a sensor is connected, derived from its ID."""

    ONEWIRE_TEMPERATURE = "onewire_temperature"
    """1-Wire temperature sensor (DS18B20), ID ``28_…``."""
    ONEWIRE_HUMIDITY = "onewire_humidity"
    """1-Wire humidity sensor (DS2438), ID ``26_…``."""
    RADIO_ROOM_CONTROLLER = "radio_room_controller"
    """Controme room controller, 6-byte MAC."""
    RADIO_SENSOR = "radio_sensor"
    """Controme radio sensor, 4-byte address."""
    VIRTUAL = "virtual"
    """Virtual or foreign system (Modbus/UniConnect), ID ``12_00_00_00_00_00_00_xx``."""
    UNKNOWN = "unknown"


class OutputType(StrEnum):
    """Kind of gateway output."""

    RELAY = "relay"
    """On/off output (FBH-Gateway Standard, Mini-Gateway): values 0/1."""
    POSITION = "position"
    """Valve position 0-100 % (FBH-Gateway PRO 0-10 V)."""
    UNKNOWN = "unknown"
    """Not configured and not (yet) detectable: a value of 1 may mean 1 % or fully open."""


class OperatingMode(StrEnum):
    """Operating mode values accepted by ``set_operating_mode`` (``betriebsart``)."""

    HEATING = "heating"
    COOLING = "cooling"
    OFF = "off"
    ON = "on"


class FpsMode(StrEnum):
    """Mode of a free programmable control block (FPS)."""

    OUTPUT = "output"
    OFFSET = "offset"


@dataclass(frozen=True, slots=True)
class SystemInfo:
    """System information (``info/``)."""

    repo: str
    branch: str
    sw_date: datetime | None
    commit: str
    hardware: str
    os: str
    services_package: bool
    app_compatible: bool
    fbi: str
    """Raw value (format differs from the other timestamps)."""


@dataclass(frozen=True, slots=True)
class Offset:
    """Temperature offset of one source, in K."""

    room: float
    house: float


@dataclass(frozen=True, slots=True)
class Sensor:
    """A sensor of a room (``temps/``).

    For radio multi-sensors Controme reports a dict as value. Its non-null entries are kept in
    ``readings``; ``value`` is then ``readings["Temperatur"]`` if present, otherwise ``None``.
    """

    id: str
    description: str
    value: float | None
    is_room_sensor: bool
    last_transmission: datetime | None
    """``None`` means "no current value", not "never transmitted"; see ``LastSeenTracker``."""
    connection: SensorConnection
    readings: Mapping[str, float] = field(default=_EMPTY)


@dataclass(frozen=True, slots=True)
class ReturnSensor:
    """A return-flow sensor (``rltemps/<room>/``). Prefer the sensors from ``temps/``."""

    id: int
    sensor_id: str
    description: str
    value: float | None
    last_transmission: datetime | None


@dataclass(frozen=True, slots=True)
class Room:
    """A room with its current state (``temps/``)."""

    id: int
    name: str
    floor_id: int
    temperature: float | None
    setpoint: float
    permanent_setpoint: float
    humidity: float | None
    humidity_status: str | None
    """Raw text Controme sends instead of a number (e.g. ``"kein Sensor vorhanden"``)."""
    total_offset: float
    offsets: Mapping[str, Offset]
    current_scene: str | None
    next_scene: str | None
    next_temperature: float | None
    next_due_time: datetime | None
    mode_end: datetime | None
    is_temporary_mode: bool
    operating_mode: str
    allowed_modes: tuple[str, ...]
    sensors: tuple[Sensor, ...]

    @property
    def room_sensor(self) -> Sensor | None:
        """The sensor marked as room temperature sensor, if any."""
        return next((s for s in self.sensors if s.is_room_sensor), None)

    @property
    def is_controlled(self) -> bool:
        """Whether Controme controls this room.

        ``temps/`` has no explicit flag. Rooms without a room temperature sensor are pseudo rooms
        that only hold system sensors (e.g. flow temperatures of a heating circuit distributor).
        """
        return self.room_sensor is not None

    @property
    def return_sensors(self) -> tuple[Sensor, ...]:
        """Return-flow sensors of a controlled room; empty for rooms without control.

        ``temps/`` does not mark them: every sensor that is neither the room sensor nor a 1-Wire
        humidity sensor counts as return-flow sensor (matches ``rltemps/`` for all recorded rooms).
        """
        if not self.is_controlled:
            return ()
        return tuple(
            s
            for s in self.sensors
            if not s.is_room_sensor and s.connection is not SensorConnection.ONEWIRE_HUMIDITY
        )

    @property
    def system_sensors(self) -> tuple[Sensor, ...]:
        """Sensors of a room without control (all of them); empty for controlled rooms."""
        return () if self.is_controlled else self.sensors


@dataclass(frozen=True, slots=True)
class Floor:
    """A floor and its rooms."""

    id: int
    name: str
    rooms: tuple[Room, ...]


@dataclass(frozen=True, slots=True)
class House:
    """A house with all floors (``temps/``)."""

    id: int
    name: str
    floors: tuple[Floor, ...]

    @property
    def rooms(self) -> tuple[Room, ...]:
        """All rooms of all floors."""
        return tuple(room for floor in self.floors for room in floor.rooms)

    @property
    def system_sensors(self) -> tuple[Sensor, ...]:
        """Sensors that serve no room as room or return-flow sensor (from rooms without control)."""
        return tuple(sensor for room in self.rooms for sensor in room.system_sensors)


@dataclass(frozen=True, slots=True)
class Output:
    """A gateway output assigned to a room (``outs/``).

    Output numbers restart per gateway, so only ``key`` is unique.
    """

    floor_id: int
    room_id: int
    number: int
    raw_value: float
    type: OutputType

    @property
    def key(self) -> tuple[int, int, int]:
        """Unique key ``(floor_id, room_id, number)``."""
        return (self.floor_id, self.room_id, self.number)

    @property
    def percent(self) -> float | None:
        """Opening in percent (0-100); relay 1 → 100. ``None`` if the type is unknown."""
        if self.type is OutputType.RELAY:
            return 100.0 if self.raw_value > 0 else 0.0
        if self.type is OutputType.POSITION:
            return float(self.raw_value)
        return None

    @property
    def open_fraction(self) -> float | None:
        """Opening as fraction (0-1). ``None`` if the type is unknown."""
        percent = self.percent
        return None if percent is None else percent / 100


@dataclass(frozen=True, slots=True)
class ActiveMode:
    """The mode currently determining a room's setpoint (``room_details/``)."""

    mode_id: int
    text: str
    setpoint: float
    module: str
    priority: int
    use_offsets: bool


@dataclass(frozen=True, slots=True)
class Scene:
    """A temperature scene available in a room."""

    id: int
    name: str
    temperature: float
    is_active: bool


@dataclass(frozen=True, slots=True)
class SmartTiming:
    """Smart Timing state: pre-heating so the next scene's temperature is reached in time."""

    time: datetime
    text: str
    state: str
    """Seen: ``rechtzeitig``, ``vorheizen``. Unknown values are passed through."""
    temperature: float


@dataclass(frozen=True, slots=True)
class SceneControl:
    """Heating program state of a room.

    ``nextDueTimeRelative`` is deliberately not exposed: it is unreliable, use ``next_due_time``.
    """

    current_scene: str | None
    next_scene: str | None
    next_temperature: float | None
    next_due_time: datetime | None
    own_schedule: bool
    """``True``: room is decoupled from the heating program."""
    smart_timing: SmartTiming | None
    mode_end: datetime | None
    after_timer_scene: str | None
    after_timer_temperature: float | None


@dataclass(frozen=True, slots=True)
class Timer:
    """Timer offset of a room.

    ``active`` may stay ``True`` long after ``end``; ``running`` is the truth.
    """

    running: bool
    active: bool
    planned: bool
    offset: float
    current_offset: float
    start: datetime | None
    end: datetime | None
    duration_minutes: int | None


@dataclass(frozen=True, slots=True)
class RoomDetails:
    """Detailed room state (``room_details/``)."""

    id: int
    room_key: str
    floor_key: str
    name: str
    icon: str | None
    current_temperature: float | None
    current_humidity: float | None
    setpoint: float
    permanent_setpoint: float
    target_temperature: float | None
    total_offset: float
    temperature_state: str
    operating_mode: str
    dominant_offset_source: str | None
    """Seen: ``wetter``, ``fps``, ``fenster_offen``. Unknown values are passed through."""
    offsets: Mapping[str, Offset]
    is_temporary_mode: bool
    gateway_offline_minutes: int | None
    floorcore_mode: str | None
    floorcore_state: str | None
    active_mode: ActiveMode | None
    scenes: tuple[Scene, ...]
    scene_control: SceneControl | None
    timer: Timer | None

    @property
    def window_open(self) -> bool:
        """``True`` while the window-open detection lowers the room temperature."""
        offset = self.offsets.get(WINDOW_OPEN_OFFSET_SOURCE)
        return offset is not None and offset.room < 0


@dataclass(frozen=True, slots=True)
class UpcomingChange:
    """A scheduled change (``upcomingoffsets/``)."""

    time: datetime
    target_id: int | None
    """Target scene for ``mode-change``; ``None`` for ``ending-list``."""
    kind: str
    """Seen: ``mode-change``, ``ending-list``. Unknown values are passed through."""


@dataclass(frozen=True, slots=True)
class UpcomingOffsets:
    """Upcoming changes per house and room, grouped by module (e.g. ``heizprogramm``)."""

    houses: Mapping[int, Mapping[str, tuple[UpcomingChange, ...]]]
    rooms: Mapping[int, Mapping[str, tuple[UpcomingChange, ...]]]


@dataclass(frozen=True, slots=True)
class FpsSlider:
    """A user variable (slider) of an FPS block."""

    value: float
    min: float | None
    max: float | None
    text: str


@dataclass(frozen=True, slots=True)
class FpsOverride:
    """Manual override of an FPS block."""

    enabled: bool
    mode: str
    until: datetime | None
    on_value: float | None
    off_value: float | None


@dataclass(frozen=True, slots=True)
class Fps:
    """A free programmable control block (``fps/``). Read-only."""

    id: int
    name: str
    mode: FpsMode
    value: float
    last_value: float | None
    formula: str
    evaluated: Mapping[str, float | str]
    inputs: Mapping[str, Mapping[str, str]]
    sliders: Mapping[str, FpsSlider]
    override: FpsOverride
    last_evaluated_at: datetime | None
    description: str
