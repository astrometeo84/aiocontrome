"""Parser for ``info/``."""

from __future__ import annotations

from datetime import tzinfo
from typing import Any

from ..models import SystemInfo
from ..sensors import parse_local_time
from ._common import expect_dict, to_str, wrap_shape_errors

SW_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@wrap_shape_errors("info/")
def parse_info(data: Any, tz: tzinfo) -> SystemInfo:
    """Parse the system information."""
    info = expect_dict(data, "info/")
    return SystemInfo(
        repo=to_str(info.get("repo")) or "",
        branch=to_str(info.get("branch")) or "",
        sw_date=parse_local_time(info.get("sw-date"), SW_DATE_FORMAT, tz),
        commit=to_str(info.get("commit")) or "",
        hardware=to_str(info.get("hw")) or "",
        os=to_str(info.get("os")) or "",
        services_package=info.get("services-paket") is True,
        app_compatible=info.get("app-compatibility") is True,
        fbi=to_str(info.get("fbi")) or "",
    )
