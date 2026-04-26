"""TLE 解析工具。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any


SECONDS_PER_DAY = 86400
MINUTES_PER_DAY = 1440
EARTH_MU_KM3_S2 = 398600.4418
EARTH_EQUATORIAL_RADIUS_KM = 6378.137


class TleParseError(ValueError):
    """TLE 文本无法按 NORAD 两行根数格式解析。"""


def calculate_tle_orbit_elements(tle_data: Mapping[str, Any]) -> dict[str, float]:
    """从已解码 TLE 字典计算数据库需要的基础轨道数据。

    返回字段:
        inclination_deg: 轨道倾角，单位度
        perigee_km: 近地点高度，单位 km
        apogee_km: 远地点高度，单位 km
        eccentricity: 离心率
    """
    inclination_deg = _required_float(
        tle_data,
        ("inclination_deg", "inclination"),
    )
    eccentricity = _required_float(tle_data, ("eccentricity",))
    mean_motion = _required_float(
        tle_data,
        ("mean_motion_rev_per_day", "mean_motion"),
    )
    if mean_motion <= 0:
        raise TleParseError("TLE 平均运动必须大于 0")

    derived_orbit = _derive_orbit_values(mean_motion, eccentricity)
    return {
        "inclination_deg": inclination_deg,
        "perigee_km": derived_orbit["perigee_km"],
        "apogee_km": derived_orbit["apogee_km"],
        "eccentricity": eccentricity,
    }


def parse_tle(tle: str, *, strict_checksum: bool = False) -> dict[str, Any]:
    """解析单组三行或两行 TLE，返回结构化字典。

    `tle` 可以包含可选名称行。该函数只解析单个目标；多颗卫星的
    TLE 列表应先拆分后逐条调用。
    """
    name, line1, line2 = _extract_tle_lines(tle)
    _validate_tle_lines(line1, line2)

    line1_checksum = int(line1[68])
    line2_checksum = int(line2[68])
    line1_checksum_valid = calculate_tle_checksum(line1) == line1_checksum
    line2_checksum_valid = calculate_tle_checksum(line2) == line2_checksum
    checksum_valid = line1_checksum_valid and line2_checksum_valid
    if strict_checksum and not checksum_valid:
        raise TleParseError("TLE 校验和不正确")

    launch_year_text = line1[9:11].strip()
    launch_number_text = line1[11:14].strip()
    launch_piece = line1[14:17].strip()
    launch_year = _expand_tle_year(int(launch_year_text)) if launch_year_text else None
    launch_number = int(launch_number_text) if launch_number_text else None
    intl_designator = line1[9:17].strip()
    international_designator = _format_international_designator(
        launch_year,
        launch_number,
        launch_piece,
    )

    epoch_year = int(line1[18:20])
    epoch_full_year = _expand_tle_year(epoch_year)
    epoch_day = float(line1[20:32])
    epoch_at = _parse_epoch(epoch_full_year, epoch_day)

    mean_motion = float(line2[52:63])
    eccentricity = _parse_implied_decimal(line2[26:33])
    inclination_deg = float(line2[8:16])
    orbit_elements = calculate_tle_orbit_elements(
        {
            "inclination_deg": inclination_deg,
            "eccentricity": eccentricity,
            "mean_motion_rev_per_day": mean_motion,
        }
    )
    derived_orbit = _derive_orbit_values(mean_motion, eccentricity)

    return {
        "name": name,
        "catalog_number": line1[2:7].strip(),
        "classification": line1[7].strip() or None,
        "intl_designator": intl_designator,
        "international_designator": international_designator,
        "international_designator_year": launch_year,
        "international_designator_launch_number": launch_number,
        "international_designator_piece": launch_piece or None,
        "epoch_year": epoch_year,
        "epoch_full_year": epoch_full_year,
        "epoch_day": epoch_day,
        "epoch_at": epoch_at,
        "mean_motion_first_derivative": _parse_float_field(line1[33:43]),
        "mean_motion_second_derivative": _parse_tle_exponential(line1[44:52]),
        "bstar": _parse_tle_exponential(line1[53:61]),
        "ephemeris_type": int(line1[62].strip() or 0),
        "element_number": int(line1[64:68]),
        "inclination_deg": orbit_elements["inclination_deg"],
        "raan_deg": float(line2[17:25]),
        "eccentricity": orbit_elements["eccentricity"],
        "argument_of_perigee_deg": float(line2[34:42]),
        "mean_anomaly_deg": float(line2[43:51]),
        "mean_motion_rev_per_day": mean_motion,
        "revolution_number_at_epoch": int(line2[63:68]),
        "checksum": {
            "line1": line1_checksum,
            "line2": line2_checksum,
        },
        "computed_checksum": {
            "line1": calculate_tle_checksum(line1),
            "line2": calculate_tle_checksum(line2),
        },
        "checksum_valid": checksum_valid,
        "line1_checksum_valid": line1_checksum_valid,
        "line2_checksum_valid": line2_checksum_valid,
        "orbital_period_minutes": derived_orbit["orbital_period_minutes"],
        "semi_major_axis_km": derived_orbit["semi_major_axis_km"],
        "perigee_km": orbit_elements["perigee_km"],
        "apogee_km": orbit_elements["apogee_km"],
        "raw_tle": "\n".join(line for line in (name, line1, line2) if line),
        "status": "有效",
        "line1": line1,
        "line2": line2,
        # 兼容现有爬虫字段命名。
        "inclination": orbit_elements["inclination_deg"],
        "raan": float(line2[17:25]),
        "arg_perigee": float(line2[34:42]),
        "mean_anomaly": float(line2[43:51]),
        "mean_motion": mean_motion,
    }


def calculate_tle_checksum(line: str) -> int:
    """计算 TLE 单行前 68 列的 modulo-10 校验和。"""
    if len(line) < 69:
        raise TleParseError("TLE 数据行必须至少包含 69 个字符")

    total = 0
    for char in line[:68]:
        if char.isdigit():
            total += int(char)
        elif char == "-":
            total += 1
    return total % 10


def _required_float(data: Mapping[str, Any], field_names: tuple[str, ...]) -> float:
    for field_name in field_names:
        value = data.get(field_name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise TleParseError(f"TLE 字段 {field_name} 必须是数字") from exc
    raise TleParseError(f"缺少 TLE 字段: {'/'.join(field_names)}")


def _extract_tle_lines(tle: str) -> tuple[str | None, str, str]:
    lines = [line.strip() for line in tle.splitlines() if line.strip()]
    if len(lines) == 2:
        name = None
        line1, line2 = lines
    elif len(lines) == 3:
        name, line1, line2 = lines
    else:
        raise TleParseError("只支持解析单组 TLE")
    return name, line1, line2


def _validate_tle_lines(line1: str, line2: str) -> None:
    if len(line1) != 69 or len(line2) != 69:
        raise TleParseError("TLE 第 1/2 行必须各为 69 个字符")
    if not line1.startswith("1 ") or not line2.startswith("2 "):
        raise TleParseError("TLE 第 1/2 行行号不正确")
    if not line1[68].isdigit() or not line2[68].isdigit():
        raise TleParseError("TLE 校验和列必须是数字")
    if line1[2:7] != line2[2:7]:
        raise TleParseError("TLE 两行的 NORAD 编号不一致")


def _expand_tle_year(two_digit_year: int) -> int:
    return 1900 + two_digit_year if two_digit_year >= 57 else 2000 + two_digit_year


def _parse_epoch(year: int, day_of_year: float) -> datetime:
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=day_of_year - 1
    )


def _parse_float_field(value: str) -> float:
    stripped = value.strip()
    if not stripped:
        return 0.0
    return float(stripped)


def _parse_implied_decimal(value: str) -> float:
    stripped = value.strip()
    if not stripped:
        return 0.0
    sign = -1 if stripped.startswith("-") else 1
    digits = stripped.lstrip("+-")
    return sign * float(f"0.{digits}")


def _parse_tle_exponential(value: str) -> float:
    field = value.strip()
    if not field:
        return 0.0

    field = field.rjust(8)
    mantissa_text = field[:6]
    exponent_text = field[6:]

    mantissa_sign = -1 if mantissa_text.startswith("-") else 1
    mantissa_digits = mantissa_text.lstrip(" +-")
    if not mantissa_digits:
        return 0.0
    return mantissa_sign * float(f"0.{mantissa_digits}") * 10 ** int(exponent_text)


def _format_international_designator(
    launch_year: int | None,
    launch_number: int | None,
    launch_piece: str,
) -> str | None:
    if launch_year is None or launch_number is None:
        return None
    return f"{launch_year}-{launch_number:03d}{launch_piece}"


def _derive_orbit_values(
    mean_motion_rev_per_day: float,
    eccentricity: float,
) -> dict[str, float | None]:
    if mean_motion_rev_per_day <= 0:
        return {
            "orbital_period_minutes": None,
            "semi_major_axis_km": None,
            "perigee_km": None,
            "apogee_km": None,
        }

    mean_motion_rad_per_second = (
        mean_motion_rev_per_day * 2 * math.pi / SECONDS_PER_DAY
    )
    semi_major_axis_km = (
        EARTH_MU_KM3_S2 / mean_motion_rad_per_second**2
    ) ** (1 / 3)
    perigee_km = semi_major_axis_km * (1 - eccentricity) - EARTH_EQUATORIAL_RADIUS_KM
    apogee_km = semi_major_axis_km * (1 + eccentricity) - EARTH_EQUATORIAL_RADIUS_KM

    return {
        "orbital_period_minutes": MINUTES_PER_DAY / mean_motion_rev_per_day,
        "semi_major_axis_km": semi_major_axis_km,
        "perigee_km": perigee_km,
        "apogee_km": apogee_km,
    }
