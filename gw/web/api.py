"""Web API 数据聚合。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from gw.database import DatabaseManager
from gw.orbit import (
    OrbitPropagationError,
    generate_previous_orbit_ground_track,
    propagate_tle_position,
)
from gw.utils.rocket import split_rocket_name_and_serial


Row = dict[str, Any]


def build_dashboard(database: DatabaseManager) -> Row:
    """构建仪表盘总览数据。"""
    groups = database.get_satellite_groups()
    satellites = list_current_satellites(database, groups)
    return {
        "summary": _build_summary(database, groups, satellites),
        "recent_satellites": _recent_satellites(satellites, limit=10),
        "recent_launches": _recent_launches(groups, limit=8),
        "manufacturers": _statistics_rows(
            database.list_manufacturers(),
            primary_sort_key="satellite_count",
        ),
        "rockets": _rocket_statistics_rows(database.list_rockets()),
    }


def list_groups(database: DatabaseManager) -> list[Row]:
    """返回组下拉和组页面需要的基础数据。"""
    return [_public_group(row) for row in database.get_satellite_groups()]


def list_satellites(database: DatabaseManager) -> list[Row]:
    """返回全部当前卫星。"""
    return _satellites(list_current_satellites(database))


def list_launches(database: DatabaseManager) -> list[Row]:
    """返回全部发射记录。"""
    return _launches(database.get_satellite_groups())


def get_group_detail(database: DatabaseManager, intl_designator: str) -> Row | None:
    """返回单组详情。"""
    detail = database.get_satellite_group_detail(intl_designator)
    if detail is None:
        return None
    return {
        **_public_group(detail),
        "satellites": [
            _public_satellite(satellite, group=detail)
            for satellite in detail.get("satellites", [])
        ],
    }


def get_satellite_detail(database: DatabaseManager, intl_designator: str) -> Row | None:
    """查找当前单星信息。"""
    normalized = str(intl_designator).strip().upper()
    if not normalized:
        return None

    for satellite in list_current_satellites(database):
        if str(satellite.get("intl_designator", "")).upper() == normalized:
            return satellite
    return None


def get_satellite_history(database: DatabaseManager, intl_designator: str) -> list[Row]:
    """返回单星历史轨道折线图数据。"""
    return [
        _history_point(row)
        for row in reversed(database.get_satellite_history(intl_designator))
    ]


def build_map_satellites(
    database: DatabaseManager,
    *,
    at: datetime | None = None,
    track_factory: Callable[..., list[Row]] = generate_previous_orbit_ground_track,
    position_factory: Callable[..., Row] = propagate_tle_position,
) -> Row:
    """返回地图页需要的组级当前位置和过去一圈地面轨迹。"""
    moment = _as_utc(at)
    groups: list[Row] = []
    skipped = 0

    for group in database.get_satellite_groups():
        raw_tle = group.get("raw_tle")
        if not raw_tle:
            skipped += 1
            continue
        try:
            position = position_factory(str(raw_tle), moment)
            track = track_factory(str(raw_tle), moment)
        except OrbitPropagationError:
            skipped += 1
            continue

        orbit = _orbit(group)
        groups.append(
            {
                "id": group["id"],
                "name": group["name"],
                "intl_designator": group["intl_designator"],
                "representative_intl_designator": _representative_intl_designator(
                    group["intl_designator"],
                ),
                "satellite_count": _int(group.get("satellite_count")),
                "valid_satellite_count": _int(group.get("valid_satellite_count")),
                "invalid_satellite_count": _int(group.get("invalid_satellite_count")),
                "orbit": orbit,
                "orbit_type": _orbit_type(orbit),
                "position": position,
                "track": track,
            }
        )

    return {
        "generated_at": moment.isoformat().replace("+00:00", "Z"),
        "groups": groups,
        "skipped_groups": skipped,
    }


def list_current_satellites(
    database: DatabaseManager,
    groups: list[Row] | None = None,
) -> list[Row]:
    """展开所有组内当前卫星。"""
    source_groups = groups if groups is not None else database.get_satellite_groups()
    satellites: list[Row] = []
    for group in source_groups:
        intl_designator = group.get("intl_designator")
        if not intl_designator:
            continue
        detail = database.get_satellite_group_detail(str(intl_designator))
        if detail is None:
            continue
        satellites.extend(
            _public_satellite(row, group=detail)
            for row in detail.get("satellites", [])
        )
    return satellites


def _build_summary(
    database: DatabaseManager,
    groups: list[Row],
    satellites: list[Row],
) -> Row:
    metainfo = database.get_metainfo()
    return {
        "total_satellites": sum(_int(row.get("satellite_count")) for row in groups),
        "valid_satellites": sum(
            _int(row.get("valid_satellite_count")) for row in groups
        ),
        "invalid_satellites": sum(
            _int(row.get("invalid_satellite_count")) for row in groups
        ),
        "tracked_satellites": len(satellites),
        "launch_groups": len(groups),
        "last_updated_at": metainfo.get("last_updated_at") if metainfo else None,
    }


def _recent_satellites(satellites: list[Row], *, limit: int) -> list[Row]:
    return _satellites(satellites, limit=limit)


def _satellites(satellites: list[Row], *, limit: int | None = None) -> list[Row]:
    ordered = sorted(
        satellites,
        key=lambda row: (
            _datetime_sort_value(row.get("launch_time")),
            DatabaseManager._intl_designator_sort_key(row["intl_designator"]),
        ),
        reverse=True,
    )
    return ordered[:limit] if limit is not None else ordered


def _recent_launches(groups: list[Row], *, limit: int) -> list[Row]:
    return _launches(groups, limit=limit)


def _launches(groups: list[Row], *, limit: int | None = None) -> list[Row]:
    ordered = sorted(
        groups,
        key=lambda row: (
            _datetime_sort_value(row.get("launch_time")),
            str(row.get("intl_designator") or ""),
        ),
        reverse=True,
    )
    selected = ordered[:limit] if limit is not None else ordered
    return [_public_launch(row) for row in selected]


def _statistics_rows(rows: list[Row], *, primary_sort_key: str) -> list[Row]:
    return sorted(
        rows,
        key=lambda row: (_int(row.get(primary_sort_key)), str(row.get("name") or "")),
        reverse=True,
    )


def _rocket_statistics_rows(rows: list[Row]) -> list[Row]:
    aggregates: dict[str, Row] = {}
    for row in rows:
        name, _serial_number = split_rocket_name_and_serial(
            str(row.get("name")) if row.get("name") is not None else None
        )
        if not name:
            continue

        item = aggregates.setdefault(
            name,
            {
                "id": row.get("id"),
                "name": name,
                "serial_number": None,
                "launch_count": 0,
                "satellite_count": 0,
            },
        )
        row_id = _int(row.get("id"))
        current_id = _int(item.get("id"))
        if row_id and (not current_id or row_id < current_id):
            item["id"] = row_id
        item["launch_count"] = _int(item.get("launch_count")) + _int(
            row.get("launch_count")
        )
        item["satellite_count"] = _int(item.get("satellite_count")) + _int(
            row.get("satellite_count")
        )

    return _statistics_rows(
        list(aggregates.values()),
        primary_sort_key="satellite_count",
    )


def _public_group(row: Row) -> Row:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "intl_designator": row.get("intl_designator"),
        "launch_time": row.get("launch_time"),
        "launch_site": row.get("launch_site"),
        "rocket_id": row.get("rocket_id"),
        "rocket_name": row.get("rocket_name"),
        "rocket_serial_number": row.get("rocket_serial_number"),
        "manufacturer_id": row.get("manufacturer_id"),
        "manufacturer_name": row.get("manufacturer_name"),
        "satellite_count": _int(row.get("satellite_count")),
        "valid_satellite_count": _int(row.get("valid_satellite_count")),
        "invalid_satellite_count": _int(row.get("invalid_satellite_count")),
        "orbit": _orbit(row),
    }


def _public_launch(row: Row) -> Row:
    return {
        "name": row.get("name"),
        "intl_designator": row.get("intl_designator"),
        "launch_time": row.get("launch_time"),
        "launch_site": row.get("launch_site"),
        "rocket_name": row.get("rocket_name"),
        "rocket_serial_number": row.get("rocket_serial_number"),
        "satellite_count": _int(row.get("satellite_count")),
        "orbit": _orbit(row),
    }


def _public_satellite(row: Row, *, group: Row) -> Row:
    return {
        "id": row.get("id"),
        "intl_designator": row.get("intl_designator"),
        "status": row.get("status") or "有效",
        "epoch_at": row.get("epoch_at"),
        "group_id": group.get("id"),
        "group_name": group.get("name"),
        "group_intl_designator": group.get("intl_designator"),
        "launch_time": group.get("launch_time"),
        "launch_site": group.get("launch_site"),
        "rocket_name": group.get("rocket_name"),
        "rocket_serial_number": group.get("rocket_serial_number"),
        "manufacturer_name": group.get("manufacturer_name"),
        "orbit": _orbit(row),
        "raw_tle": row.get("raw_tle"),
    }


def _history_point(row: Row) -> Row:
    return {
        "id": row.get("id"),
        "epoch_at": row.get("epoch_at"),
        "perigee_km": row.get("perigee_km"),
        "apogee_km": row.get("apogee_km"),
    }


def _orbit(row: Row) -> Row:
    return {
        "inclination_deg": row.get("inclination_deg"),
        "perigee_km": row.get("perigee_km"),
        "apogee_km": row.get("apogee_km"),
        "eccentricity": row.get("eccentricity"),
    }


def _representative_intl_designator(group_intl_designator: Any) -> str | None:
    if group_intl_designator is None:
        return None
    value = str(group_intl_designator).strip()
    return f"{value}A" if value else None


def _orbit_type(orbit: Row) -> str:
    perigee = orbit.get("perigee_km")
    apogee = orbit.get("apogee_km")
    if perigee is not None and float(perigee) >= 35000:
        return "geo"
    if apogee is not None and float(apogee) >= 35000:
        return "geo"
    return "leo"


def _datetime_sort_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)
