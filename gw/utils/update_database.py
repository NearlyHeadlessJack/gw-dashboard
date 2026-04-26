"""数据库更新工具。"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from gw.database import DatabaseManager
from gw.scraper.celestrak import fetch_group_tle_data
from gw.scraper.huiji import fetch_satellite_groups
from gw.utils.update_progress import NullUpdateProgressReporter, UpdateProgressReporter
from gw.utils.rocket import normalize_rocket_model_name, split_rocket_name_and_serial


logger = logging.getLogger(__name__)

HuijiGroupFetcher = Callable[[], list[dict[str, Any]]]
GroupTleFetcher = Callable[[str, int], list[dict[str, Any]]]


@dataclass(frozen=True)
class DatabaseUpdateResult:
    """数据库更新结果摘要。"""

    groups_updated: int
    manufacturers_updated: int
    rockets_updated: int
    group_satellites_updated: int
    satellite_records_added: int


@dataclass(frozen=True)
class _NormalizedGroup:
    name: str
    intl_designator: str
    satellite_count: int
    manufacturer_name: str | None
    rocket_name: str | None
    rocket_serial_number: str | None
    launch_time: datetime | None
    launch_site: str | None


def update_satellite_database(
    database: DatabaseManager,
    *,
    huiji_group_fetcher: HuijiGroupFetcher = fetch_satellite_groups,
    group_tle_fetcher: GroupTleFetcher = fetch_group_tle_data,
    now: datetime | None = None,
    update_metainfo: bool = True,
    progress_reporter: UpdateProgressReporter | None = None,
) -> DatabaseUpdateResult:
    """从灰机 wiki 和 TLE 源更新数据库。

    灰机 wiki 表只提供组级信息；组表和单星历史表均保存原始 TLE，
    轨道数值由查询接口按需解码。
    """
    progress = progress_reporter or NullUpdateProgressReporter()
    logger.info("data update starting: initializing database schema")
    database.initialize_database()
    logger.info("crawler starting: fetching satellite groups from huiji wiki")
    progress.launch_fetch_started()
    groups = [
        group
        for group in (_normalize_group_row(row) for row in huiji_group_fetcher())
        if group is not None
    ]
    progress.launch_fetch_finished(len(groups))
    logger.info("crawler complete: parsed %s satellite groups", len(groups))

    manufacturer_ids = _upsert_manufacturers(database, groups)
    rocket_ids = _upsert_rockets(database, groups)
    logger.info(
        "data update upserted statistics: manufacturers=%s rockets=%s",
        len(manufacturer_ids),
        len(rocket_ids),
    )

    group_ids: dict[str, int] = {}
    for group in groups:
        group_ids[group.intl_designator] = _upsert_satellite_group(
            database,
            group,
            manufacturer_id=(
                manufacturer_ids.get(group.manufacturer_name)
                if group.manufacturer_name
                else None
            ),
            rocket_id=(
                rocket_ids.get((group.rocket_name, group.rocket_serial_number))
                if group.rocket_name
                else None
            ),
        )

    group_satellites_updated = 0
    satellite_records_added = 0
    tle_groups = [group for group in groups if group.satellite_count > 0]
    progress.tle_fetch_started(len(tle_groups))
    tle_group_index = 0
    for group in groups:
        if group.satellite_count <= 0:
            logger.info(
                "crawler skipping group %s: satellite_count=%s",
                group.intl_designator,
                group.satellite_count,
            )
            continue

        tle_group_index += 1
        logger.info(
            "crawler starting: fetching TLE for group=%s expected_satellites=%s",
            group.intl_designator,
            group.satellite_count,
        )
        progress.tle_group_started(
            tle_group_index,
            len(tle_groups),
            group.intl_designator,
        )
        try:
            parsed_tles = sorted(
                group_tle_fetcher(group.intl_designator, group.satellite_count),
                key=lambda item: DatabaseManager._intl_designator_sort_key(
                    _satellite_intl_designator(item) or ""
                ),
            )
        except Exception:
            progress.tle_group_failed(
                tle_group_index,
                len(tle_groups),
                group.intl_designator,
            )
            raise
        progress.tle_group_finished(
            tle_group_index,
            len(tle_groups),
            group.intl_designator,
            len(parsed_tles),
        )
        logger.info(
            "crawler complete: group=%s tle_records=%s",
            group.intl_designator,
            len(parsed_tles),
        )
        if not parsed_tles:
            continue

        group_id = group_ids[group.intl_designator]
        existing_satellites = {
            satellite["intl_designator"]: satellite
            for satellite in database.list_group_satellites(group_id)
        }
        group_first_tle_raw: str | None = None
        valid_satellite_count = 0
        invalid_satellite_count = 0

        for parsed_tle in parsed_tles:
            raw_tle = _raw_tle_from_parsed(parsed_tle)
            satellite_intl_designator = _satellite_intl_designator(parsed_tle)
            if not raw_tle or not satellite_intl_designator:
                continue
            if group_first_tle_raw is None:
                group_first_tle_raw = raw_tle
            status = _normalize_satellite_status(parsed_tle.get("status"))
            if status == "有效":
                valid_satellite_count += 1
            else:
                invalid_satellite_count += 1

            epoch_at = parsed_tle.get("epoch_at")
            if not isinstance(epoch_at, datetime):
                epoch_at = now or datetime.now(timezone.utc)

            existing = existing_satellites.get(satellite_intl_designator)
            if existing:
                database.update_group_satellite(
                    group_id,
                    existing["id"],
                    epoch_at=epoch_at,
                    status=status,
                    raw_tle=raw_tle,
                )
            else:
                record_id = database.add_group_satellite(
                    group_id,
                    epoch_at=epoch_at,
                    intl_designator=satellite_intl_designator,
                    status=status,
                    raw_tle=raw_tle,
                )
                existing_satellites[satellite_intl_designator] = {
                    "id": record_id,
                    "intl_designator": satellite_intl_designator,
                }
            group_satellites_updated += 1

            database.add_satellite_record(
                satellite_intl_designator,
                epoch_at=epoch_at,
                raw_tle=raw_tle,
            )
            satellite_records_added += 1

        database.update_satellite_group(
            group_id,
            raw_tle=group_first_tle_raw,
            valid_satellite_count=valid_satellite_count,
            invalid_satellite_count=invalid_satellite_count,
        )
        logger.info(
            "data update group saved: group=%s valid=%s invalid=%s",
            group.intl_designator,
            valid_satellite_count,
            invalid_satellite_count,
        )
    progress.tle_fetch_finished(len(tle_groups))

    if update_metainfo:
        _mark_database_updated(database, now or datetime.now(timezone.utc))

    result = DatabaseUpdateResult(
        groups_updated=len(groups),
        manufacturers_updated=len(manufacturer_ids),
        rockets_updated=len(rocket_ids),
        group_satellites_updated=group_satellites_updated,
        satellite_records_added=satellite_records_added,
    )
    logger.info(
        "data update complete: groups=%s manufacturers=%s rockets=%s "
        "group_satellites=%s satellite_records=%s",
        result.groups_updated,
        result.manufacturers_updated,
        result.rockets_updated,
        result.group_satellites_updated,
        result.satellite_records_added,
    )
    return result


def _upsert_manufacturers(
    database: DatabaseManager,
    groups: Iterable[_NormalizedGroup],
) -> dict[str, int]:
    aggregates: dict[str, dict[str, int]] = defaultdict(
        lambda: {"group_count": 0, "satellite_count": 0}
    )
    for group in groups:
        if not group.manufacturer_name:
            continue
        aggregates[group.manufacturer_name]["group_count"] += 1
        aggregates[group.manufacturer_name]["satellite_count"] += group.satellite_count

    existing = {item["name"]: item for item in database.list_manufacturers()}
    result: dict[str, int] = {}
    for name, counts in aggregates.items():
        if name in existing:
            manufacturer_id = existing[name]["id"]
            database.update_manufacturer(manufacturer_id, **counts)
        else:
            manufacturer_id = database.create_manufacturer(name, **counts)
        result[name] = manufacturer_id
    return result


def _upsert_rockets(
    database: DatabaseManager,
    groups: Iterable[_NormalizedGroup],
) -> dict[tuple[str, str | None], int]:
    aggregates: dict[tuple[str, str | None], dict[str, int]] = defaultdict(
        lambda: {"launch_count": 0, "satellite_count": 0}
    )
    for group in groups:
        if not group.rocket_name:
            continue
        key = (
            normalize_rocket_model_name(group.rocket_name) or group.rocket_name,
            group.rocket_serial_number,
        )
        aggregates[key]["launch_count"] += 1
        aggregates[key]["satellite_count"] += group.satellite_count

    existing: dict[tuple[str, str | None], dict[str, Any]] = {}
    for item in database.list_rockets():
        key = _existing_rocket_key(item)
        if key[0] and key not in existing:
            existing[key] = item

    result: dict[tuple[str, str | None], int] = {}
    for (name, serial_number), counts in aggregates.items():
        if (name, serial_number) in existing:
            rocket_id = existing[(name, serial_number)]["id"]
            database.update_rocket(
                rocket_id,
                name=name,
                serial_number=serial_number,
                **counts,
            )
        else:
            rocket_id = database.create_rocket(
                name,
                serial_number=serial_number,
                **counts,
            )
        result[(name, serial_number)] = rocket_id
    return result


def _existing_rocket_key(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    raw_name = row.get("name")
    name, embedded_serial = split_rocket_name_and_serial(
        str(raw_name) if raw_name is not None else None
    )
    raw_serial = row.get("serial_number")
    serial_number = (
        _clean_text(str(raw_serial)) if raw_serial is not None else embedded_serial
    )
    return name, serial_number


def _upsert_satellite_group(
    database: DatabaseManager,
    group: _NormalizedGroup,
    *,
    manufacturer_id: int | None,
    rocket_id: int | None,
) -> int:
    existing = database.get_satellite_group_by_intl_designator(group.intl_designator)
    fields = {
        "name": group.name,
        "intl_designator": group.intl_designator,
        "launch_time": group.launch_time,
        "launch_site": group.launch_site,
        "rocket_id": rocket_id,
        "manufacturer_id": manufacturer_id,
        "satellite_count": group.satellite_count,
        "valid_satellite_count": 0,
        "invalid_satellite_count": 0,
    }
    if existing:
        database.update_satellite_group(existing["id"], **fields)
        return int(existing["id"])
    return database.create_satellite_group(**fields)


def _normalize_group_row(row: Mapping[str, Any]) -> _NormalizedGroup | None:
    intl_designator = _normalize_group_intl_designator(_first_text(row, "COSPAR", "国际识别号"))
    if not intl_designator:
        return None

    rocket_name, rocket_serial_number = split_rocket_name_and_serial(
        _first_text(row, "运载火箭", "发射火箭")
    )
    return _NormalizedGroup(
        name=_normalize_group_name(_first_text(row, "名称") or intl_designator),
        intl_designator=intl_designator,
        satellite_count=_parse_int(_first_text(row, "部署颗数", "卫星数量", "数量")),
        manufacturer_name=_clean_text(_first_text(row, "研制单位")),
        rocket_name=rocket_name,
        rocket_serial_number=rocket_serial_number,
        launch_time=_parse_datetime(_first_text(row, "发射时间", "发射日期")),
        launch_site=_clean_text(_first_text(row, "发射地点", "发射场")),
    )


def _first_text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _normalize_group_name(name: str) -> str:
    cleaned = _clean_text(name) or name
    if "组" in cleaned:
        return cleaned[: cleaned.index("组") + 1]
    return cleaned


def _normalize_group_intl_designator(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(\d{4})[-\s]?(\d{3})", value)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def _satellite_intl_designator(parsed_tle: Mapping[str, Any]) -> str | None:
    value = (
        parsed_tle.get("international_designator")
        or parsed_tle.get("intl_designator")
    )
    if value is None:
        return None

    normalized = str(value).strip().upper()
    full_match = re.fullmatch(r"(\d{4})[-\s]?(\d{3})([A-Z]{1,3})", normalized)
    if full_match:
        return f"{full_match.group(1)}-{full_match.group(2)}{full_match.group(3)}"

    short_match = re.fullmatch(r"(\d{2})(\d{3})([A-Z]{1,3})", normalized)
    if short_match:
        year = int(short_match.group(1))
        full_year = 1900 + year if year >= 57 else 2000 + year
        return f"{full_year}-{short_match.group(2)}{short_match.group(3)}"

    return normalized or None


def _raw_tle_from_parsed(parsed_tle: Mapping[str, Any]) -> str | None:
    raw_tle = parsed_tle.get("raw_tle")
    if raw_tle is not None and str(raw_tle).strip():
        return str(raw_tle)

    line1 = parsed_tle.get("line1")
    line2 = parsed_tle.get("line2")
    if not line1 or not line2:
        return None
    name = parsed_tle.get("name")
    return "\n".join(str(item) for item in (name, line1, line2) if item)


def _normalize_satellite_status(value: Any) -> str:
    if value is None:
        return "有效"
    return "失效" if str(value).strip() == "失效" else "有效"


def _parse_int(value: str | None) -> int:
    if not value:
        return 0
    match = re.search(r"\d+", value)
    return int(match.group()) if match else 0


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = (
        cleaned.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
    )
    match = re.search(
        r"(\d{4}-\d{1,2}-\d{1,2})(?:\s*(\d{1,2}:\d{2}(?::\d{2})?))?",
        cleaned,
    )
    if not match:
        return None

    time_part = match.group(2) or "00:00:00"
    if len(time_part.split(":")) == 2:
        time_part = f"{time_part}:00"
    return datetime.fromisoformat(f"{match.group(1)} {time_part}")


def _mark_database_updated(database: DatabaseManager, updated_at: datetime) -> None:
    metainfo = database.get_metainfo()
    database.set_metainfo(
        updated_at,
        valid_duration_seconds=(
            metainfo["valid_duration_seconds"] if metainfo else 86400
        ),
        satellite_record_limit=(
            metainfo["satellite_record_limit"] if metainfo else None
        ),
    )
