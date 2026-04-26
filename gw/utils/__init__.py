"""通用工具函数。"""

from gw.utils.tle import (
    TleParseError,
    calculate_tle_checksum,
    calculate_tle_orbit_elements,
    parse_tle,
)
from gw.utils.rocket import normalize_rocket_model_name, split_rocket_name_and_serial

__all__ = [
    "DatabaseUpdateResult",
    "TleParseError",
    "calculate_tle_checksum",
    "calculate_tle_orbit_elements",
    "normalize_rocket_model_name",
    "parse_tle",
    "split_rocket_name_and_serial",
    "update_satellite_database",
]


def __getattr__(name: str):
    if name in {"DatabaseUpdateResult", "update_satellite_database"}:
        from gw.utils.update_database import (
            DatabaseUpdateResult,
            update_satellite_database,
        )

        values = {
            "DatabaseUpdateResult": DatabaseUpdateResult,
            "update_satellite_database": update_satellite_database,
        }
        return values[name]
    raise AttributeError(name)
