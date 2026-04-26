"""Celestrak TLE 轨道数据获取。

通过国际识别号（INTDES）从 Celestrak 获取 TLE 数据，
用于计算卫星的实时轨道位置。
"""

import re

from curl_cffi import requests

from gw.utils.tle import TleParseError, parse_tle as parse_single_tle

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"


def fetch_tle(
    intl_designator: str,
    url: str = CELESTRAK_URL,
    timeout: int | None = None,
) -> str:
    """从 Celestrak 获取 TLE 原始文本。

    参数:
        intl_designator: 国际识别号，如 "2024-240"（整组）或 "2024-240A"（单颗）
    """
    kwargs = {"params": {"INTDES": intl_designator}}
    if timeout is not None:
        kwargs["timeout"] = timeout
    resp = requests.get(url, **kwargs)
    resp.raise_for_status()
    return resp.text


def parse_tle(tle_text: str) -> list[dict]:
    """解析 TLE 文本为结构化数据。

    返回字典包含: name, catalog_number, intl_designator, epoch_year,
    epoch_day, inclination, raan, eccentricity, arg_perigee, mean_anomaly,
    mean_motion, line1, line2
    """
    lines = [line.strip() for line in tle_text.strip().split("\n") if line.strip()]
    satellites = []
    i = 0
    while i + 2 < len(lines):
        name = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]

        if not line1.startswith("1 ") or not line2.startswith("2 "):
            i += 1
            continue

        try:
            satellites.append(parse_single_tle("\n".join((name, line1, line2))))
        except TleParseError:
            pass
        i += 3

    return satellites


def fetch_tle_data(intl_designator: str) -> list[dict]:
    """获取并解析 TLE 数据（fetch_tle + parse_tle 的便捷组合）。"""
    tle_text = fetch_tle(intl_designator)
    return parse_tle(tle_text)


def fetch_group_tle_data(intl_designator: str, satellite_count: int) -> list[dict]:
    """获取某组前 satellite_count 颗卫星的 TLE 数据。

    Celestrak 用组国际识别号查询时，可能额外返回末级火箭等对象。
    星网卫星在同一组内按国际识别号对象字母段排序，因此这里先按
    国际识别号排序，再只取前 satellite_count 条。
    """
    if satellite_count < 0:
        raise ValueError("satellite_count 不能为负数")
    if satellite_count == 0:
        return []

    tle_text = fetch_tle(intl_designator)
    satellites = parse_tle(tle_text)
    return sorted(satellites, key=_intl_designator_sort_key)[:satellite_count]


def _intl_designator_sort_key(satellite: dict) -> tuple[str, int, str]:
    intl_designator = str(satellite.get("intl_designator", ""))
    launch_key, piece = _split_intl_designator(intl_designator)
    return (launch_key, _piece_rank(piece), intl_designator)


def _split_intl_designator(intl_designator: str) -> tuple[str, str]:
    normalized = intl_designator.strip().upper().replace("-", "")
    match = re.fullmatch(r"(\d{5})([A-Z]{0,3})", normalized)
    if match:
        return match.group(1), match.group(2)

    match = re.fullmatch(r"(\d{7})([A-Z]{0,3})", normalized)
    if match:
        year = match.group(1)[:4]
        launch_number = match.group(1)[4:]
        return f"{year[-2:]}{launch_number}", match.group(2)

    return normalized, ""


def _piece_rank(piece: str) -> int:
    rank = 0
    for char in piece:
        rank = rank * 26 + (ord(char) - ord("A") + 1)
    return rank
