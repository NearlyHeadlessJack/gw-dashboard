"""基于 TLE 的卫星当前位置与地面轨迹计算。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sgp4.api import Satrec, jday


EARTH_EQUATORIAL_RADIUS_KM = 6378.137
EARTH_FLATTENING = 1 / 298.257223563
EARTH_ECCENTRICITY_SQUARED = EARTH_FLATTENING * (2 - EARTH_FLATTENING)


class OrbitPropagationError(ValueError):
    """TLE 无法传播到指定时间。"""


def propagate_tle_position(
    raw_tle: str,
    at: datetime | None = None,
) -> dict[str, float]:
    """返回指定时刻的经纬度和高度。

    坐标为 WGS-84 近似经纬度，适合前端地图展示；轨道传播由 sgp4 完成。
    """
    moment = _normalize_datetime(at)
    line1, line2 = _extract_tle_lines(raw_tle)
    satellite = Satrec.twoline2rv(line1, line2)
    jd, fraction = _julian_day(moment)
    error_code, position_km, _velocity_km_s = satellite.sgp4(jd, fraction)
    if error_code != 0:
        raise OrbitPropagationError(f"SGP4 传播失败，错误码: {error_code}")

    latitude, longitude, altitude = _teme_to_geodetic(position_km, jd + fraction)
    return {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "altitude_km": round(altitude, 3),
    }


def generate_ground_track(
    raw_tle: str,
    at: datetime | None = None,
    *,
    minutes_before: int = 45,
    minutes_after: int = 45,
    step_minutes: int = 5,
) -> list[dict[str, float]]:
    """生成指定时刻前后一段时间的地面轨迹点。"""
    if minutes_before < 0 or minutes_after < 0:
        raise OrbitPropagationError("轨迹时间范围不能为负数")
    if step_minutes <= 0:
        raise OrbitPropagationError("轨迹步长必须大于 0")

    center = _normalize_datetime(at)
    start = center - timedelta(minutes=minutes_before)
    total_minutes = minutes_before + minutes_after
    point_count = total_minutes // step_minutes + 1

    points: list[dict[str, float]] = []
    for index in range(point_count):
        moment = start + timedelta(minutes=index * step_minutes)
        point = propagate_tle_position(raw_tle, moment)
        point["timestamp"] = moment.isoformat().replace("+00:00", "Z")
        points.append(point)
    return points


def _normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _julian_day(value: datetime) -> tuple[float, float]:
    seconds = value.second + value.microsecond / 1_000_000
    return jday(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        seconds,
    )


def _extract_tle_lines(raw_tle: str) -> tuple[str, str]:
    lines = [line.strip() for line in str(raw_tle).splitlines() if line.strip()]
    tle_lines = [line for line in lines if line.startswith(("1 ", "2 "))]
    if len(tle_lines) < 2:
        raise OrbitPropagationError("缺少 TLE 两行根数")
    line1, line2 = tle_lines[0], tle_lines[1]
    if not line1.startswith("1 ") or not line2.startswith("2 "):
        raise OrbitPropagationError("TLE 行号不正确")
    return line1, line2


def _teme_to_geodetic(position_km: Any, julian_day: float) -> tuple[float, float, float]:
    x_eci, y_eci, z_eci = (float(position_km[0]), float(position_km[1]), float(position_km[2]))
    theta = _greenwich_mean_sidereal_time(julian_day)

    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)
    x = cos_theta * x_eci + sin_theta * y_eci
    y = -sin_theta * x_eci + cos_theta * y_eci
    z = z_eci

    longitude = math.atan2(y, x)
    latitude, altitude = _ecef_to_geodetic_latitude_altitude(x, y, z)
    longitude_deg = (math.degrees(longitude) + 540) % 360 - 180
    return math.degrees(latitude), longitude_deg, altitude


def _greenwich_mean_sidereal_time(julian_day: float) -> float:
    centuries = (julian_day - 2451545.0) / 36525.0
    gmst_deg = (
        280.46061837
        + 360.98564736629 * (julian_day - 2451545.0)
        + 0.000387933 * centuries**2
        - centuries**3 / 38710000.0
    )
    return math.radians(gmst_deg % 360)


def _ecef_to_geodetic_latitude_altitude(
    x: float,
    y: float,
    z: float,
) -> tuple[float, float]:
    radius_xy = math.hypot(x, y)
    latitude = math.atan2(z, radius_xy * (1 - EARTH_ECCENTRICITY_SQUARED))

    altitude = 0.0
    for _ in range(7):
        sin_latitude = math.sin(latitude)
        prime_vertical_radius = EARTH_EQUATORIAL_RADIUS_KM / math.sqrt(
            1 - EARTH_ECCENTRICITY_SQUARED * sin_latitude**2
        )
        altitude = radius_xy / max(math.cos(latitude), 1e-12) - prime_vertical_radius
        latitude = math.atan2(
            z,
            radius_xy
            * (
                1
                - EARTH_ECCENTRICITY_SQUARED
                * prime_vertical_radius
                / (prime_vertical_radius + altitude)
            ),
        )
    return latitude, altitude
