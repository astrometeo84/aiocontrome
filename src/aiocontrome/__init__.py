"""Async client for the local HTTP API of Controme Smart-Heat."""

from importlib.metadata import version

from .client import DEFAULT_DURATION, ContromeClient, Duration, basic_auth_header
from .errors import (
    ContromeApiDisabledError,
    ContromeAuthError,
    ContromeConnectionError,
    ContromeError,
    ContromeNotFoundError,
    ContromeResponseError,
)
from .models import (
    ActiveMode,
    Floor,
    Fps,
    FpsMode,
    FpsOverride,
    FpsSlider,
    House,
    Offset,
    OperatingMode,
    Output,
    OutputType,
    ReturnSensor,
    Room,
    RoomDetails,
    Scene,
    SceneControl,
    Sensor,
    SensorConnection,
    SmartTiming,
    SystemInfo,
    Timer,
    UpcomingChange,
    UpcomingOffsets,
)
from .outputs import OutputTypeDetector
from .redact import REDACTED, redact
from .sensors import LastSeenTracker, detect_connection, is_stale

__version__ = version("aiocontrome")
"""Installed package version (single source: ``pyproject.toml``)."""

__all__ = [
    "DEFAULT_DURATION",
    "REDACTED",
    "ActiveMode",
    "ContromeApiDisabledError",
    "ContromeAuthError",
    "ContromeClient",
    "ContromeConnectionError",
    "ContromeError",
    "ContromeNotFoundError",
    "ContromeResponseError",
    "Duration",
    "Floor",
    "Fps",
    "FpsMode",
    "FpsOverride",
    "FpsSlider",
    "House",
    "LastSeenTracker",
    "Offset",
    "OperatingMode",
    "Output",
    "OutputType",
    "OutputTypeDetector",
    "ReturnSensor",
    "Room",
    "RoomDetails",
    "Scene",
    "SceneControl",
    "Sensor",
    "SensorConnection",
    "SmartTiming",
    "SystemInfo",
    "Timer",
    "UpcomingChange",
    "UpcomingOffsets",
    "__version__",
    "basic_auth_header",
    "detect_connection",
    "is_stale",
    "redact",
]
