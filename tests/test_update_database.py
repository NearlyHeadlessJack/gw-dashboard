from datetime import datetime, timezone
import logging

import pytest

from gw.database import DatabaseConfigurationError, DatabaseManager
from gw.utils import parse_tle, update_satellite_database


RAW_TLE_A = """\
HULIANWANG DIGUI-01
1 62323U 24240A   26115.49220466  .00000041  00000+0  60880-4 0  9996
2 62323  86.5040   1.0150 0001837  72.4834 287.6500 13.24413432 65663
"""

RAW_TLE_B = """\
HULIANWANG DIGUI-02
1 62324U 24240B   26115.49966838  .00000039  00000+0  57141-4 0  9990
2 62324  86.5069   1.1568 0001856  73.6881 286.4457 13.24412762 65679
"""

RAW_TLE_C = """\
HULIANWANG DIGUI-03
1 62325U 24240C   26115.48454868  .00000056  00000+0  96273-4 0  9993
2 62325  86.5022   0.9286 0001766  71.6719 288.4607 13.24412313 65661
"""


@pytest.fixture
def db():
    manager = DatabaseManager("sqlite3", ":memory:")
    manager.initialize_database()
    return manager


def test_update_satellite_database_updates_group_related_tables_and_tle_data(db):
    now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    huiji_rows = [
        {
            "名称": "低轨卫星11组A-E星",
            "COSPAR": "2024-240",
            "部署颗数": "2颗",
            "研制单位": "五院",
            "发射时间": "2024年12月16日 18:00",
            "运载火箭": "长征六号改 Y9",
            "发射地点": "太原",
        }
    ]
    tle_calls = []

    def fake_group_tle_fetcher(intl_designator, satellite_count):
        tle_calls.append((intl_designator, satellite_count))
        return [parse_tle(RAW_TLE_B), parse_tle(RAW_TLE_A)]

    result = update_satellite_database(
        db,
        huiji_group_fetcher=lambda: huiji_rows,
        group_tle_fetcher=fake_group_tle_fetcher,
        now=now,
    )

    assert result.groups_updated == 1
    assert result.manufacturers_updated == 1
    assert result.rockets_updated == 1
    assert result.group_satellites_updated == 2
    assert result.satellite_records_added == 2
    assert tle_calls == [("2024-240", 2)]

    manufacturer = db.list_manufacturers()[0]
    assert manufacturer["name"] == "五院"
    assert manufacturer["group_count"] == 1
    assert manufacturer["satellite_count"] == 2

    rocket = db.list_rockets()[0]
    assert rocket["name"] == "长征六号改"
    assert rocket["serial_number"] == "Y9"
    assert rocket["launch_count"] == 1
    assert rocket["satellite_count"] == 2

    group = db.get_satellite_group_by_intl_designator("2024-240")
    assert group["name"] == "低轨卫星11组"
    assert group["launch_time"] == datetime(2024, 12, 16, 18, 0)
    assert group["launch_site"] == "太原"
    assert group["rocket_id"] == rocket["id"]
    assert group["manufacturer_id"] == manufacturer["id"]
    assert group["satellite_count"] == 2
    assert group["valid_satellite_count"] == 2
    assert group["invalid_satellite_count"] == 0
    assert group["raw_tle"] == parse_tle(RAW_TLE_A)["raw_tle"]
    assert group["inclination_deg"] == pytest.approx(parse_tle(RAW_TLE_A)["inclination_deg"])

    group_satellites = db.list_group_satellites(group["id"])
    assert [item["intl_designator"] for item in group_satellites] == [
        "2024-240A",
        "2024-240B",
    ]
    assert [item["status"] for item in group_satellites] == ["有效", "有效"]
    assert [item["raw_tle"] for item in group_satellites] == [
        parse_tle(RAW_TLE_A)["raw_tle"],
        parse_tle(RAW_TLE_B)["raw_tle"],
    ]

    assert db.get_satellite_history("2024-240A")[0]["raw_tle"] == parse_tle(RAW_TLE_A)["raw_tle"]
    assert db.get_satellite_history("2024-240B")[0]["raw_tle"] == parse_tle(RAW_TLE_B)["raw_tle"]
    assert db.get_metainfo()["last_updated_at"] == now.replace(tzinfo=None)


def test_update_satellite_database_reuses_existing_rows_on_second_update(db):
    first_rows = [
        {
            "名称": "低轨01组A-B星",
            "COSPAR": "2024-240",
            "部署颗数": "2",
            "研制单位": "五院",
            "运载火箭": "长征六号改 Y9",
        }
    ]
    second_rows = [
        {
            "名称": "低轨01组A-B星",
            "COSPAR": "2024-240",
            "部署颗数": "1",
            "研制单位": "五院",
            "运载火箭": "长征六号改 Y9",
        }
    ]

    update_satellite_database(
        db,
        huiji_group_fetcher=lambda: first_rows,
        group_tle_fetcher=lambda intl_designator, satellite_count: [
            parse_tle(RAW_TLE_A),
            parse_tle(RAW_TLE_B),
        ],
        update_metainfo=False,
    )
    group = db.get_satellite_group_by_intl_designator("2024-240")

    update_satellite_database(
        db,
        huiji_group_fetcher=lambda: second_rows,
        group_tle_fetcher=lambda intl_designator, satellite_count: [
            parse_tle(RAW_TLE_A)
        ],
        update_metainfo=False,
    )

    assert len(db.list_satellite_groups()) == 1
    assert len(db.list_manufacturers()) == 1
    assert len(db.list_rockets()) == 1
    assert db.get_satellite_group_by_intl_designator("2024-240")["id"] == group["id"]
    assert len(db.list_group_satellites(group["id"])) == 2
    assert db.list_group_satellites(group["id"])[0]["raw_tle"] == parse_tle(RAW_TLE_A)["raw_tle"]
    assert len(db.get_satellite_history("2024-240A")) == 2


def test_update_satellite_database_counts_invalid_satellite_status(db):
    invalid_tle = parse_tle(RAW_TLE_B)
    invalid_tle["status"] = "失效"

    update_satellite_database(
        db,
        huiji_group_fetcher=lambda: [
            {
                "名称": "低轨01组A-B星",
                "COSPAR": "2024-240",
                "部署颗数": "2",
            }
        ],
        group_tle_fetcher=lambda intl_designator, satellite_count: [
            parse_tle(RAW_TLE_A),
            invalid_tle,
        ],
        update_metainfo=False,
    )

    group = db.get_satellite_group_by_intl_designator("2024-240")
    assert group["valid_satellite_count"] == 1
    assert group["invalid_satellite_count"] == 1
    assert [item["status"] for item in db.list_group_satellites(group["id"])] == [
        "有效",
        "失效",
    ]


def test_update_satellite_database_skips_rows_without_group_intl_designator(db):
    result = update_satellite_database(
        db,
        huiji_group_fetcher=lambda: [{"名称": "无 COSPAR", "部署颗数": "2"}],
        group_tle_fetcher=lambda intl_designator, satellite_count: [
            parse_tle(RAW_TLE_A)
        ],
        update_metainfo=False,
    )

    assert result.groups_updated == 0
    assert db.list_satellite_groups() == []


def test_update_satellite_database_rejects_removed_orbit_write_fields(db):
    group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2024-240",
    )

    with pytest.raises(DatabaseConfigurationError, match="不支持的字段"):
        db.update_satellite_group(group_id, eccentricity=0.0001)


def test_update_satellite_database_logs_progress(db, caplog):
    with caplog.at_level(logging.INFO, logger="gw.utils.update_database"):
        update_satellite_database(
            db,
            huiji_group_fetcher=lambda: [
                {
                    "名称": "低轨01组A星",
                    "COSPAR": "2024-240",
                    "部署颗数": "1",
                }
            ],
            group_tle_fetcher=lambda intl_designator, satellite_count: [
                parse_tle(RAW_TLE_A)
            ],
            update_metainfo=False,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("data update starting" in message for message in messages)
    assert any("crawler starting: fetching satellite groups" in message for message in messages)
    assert any("crawler starting: fetching TLE for group=2024-240" in message for message in messages)
    assert any("data update complete" in message for message in messages)


def test_update_satellite_database_parses_launch_time_without_space(db):
    update_satellite_database(
        db,
        huiji_group_fetcher=lambda: [
            {
                "名称": "低轨01组A星",
                "COSPAR": "2024-240",
                "部署颗数": "1",
                "发射时间": "2024年12月16日18:00",
            }
        ],
        group_tle_fetcher=lambda intl_designator, satellite_count: [
            parse_tle(RAW_TLE_A)
        ],
        update_metainfo=False,
    )

    group = db.get_satellite_group_by_intl_designator("2024-240")
    assert group["launch_time"] == datetime(2024, 12, 16, 18, 0)
