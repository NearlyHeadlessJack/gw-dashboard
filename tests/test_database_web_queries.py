from datetime import datetime

import pytest
from sqlalchemy import text

from gw.database import (
    DatabaseConfigurationError,
    DatabaseManager,
    DatabaseQueryError,
)
from gw.utils import parse_tle


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


def assert_decoded_orbit(row, raw_tle):
    decoded = parse_tle(raw_tle)
    assert row["inclination_deg"] == pytest.approx(decoded["inclination_deg"])
    assert row["perigee_km"] == pytest.approx(decoded["perigee_km"])
    assert row["apogee_km"] == pytest.approx(decoded["apogee_km"])
    assert row["eccentricity"] == pytest.approx(decoded["eccentricity"])


@pytest.fixture
def db():
    manager = DatabaseManager("sqlite3", ":memory:")
    manager.initialize_database()
    return manager


def test_get_satellite_history_returns_records_newest_epoch_first(db):
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle=RAW_TLE_A,
    )
    newest_id = db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 20),
        raw_tle=RAW_TLE_B,
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 10),
        raw_tle=RAW_TLE_C,
    )

    records = db.get_satellite_history("2024-240A")

    assert [record["raw_tle"] for record in records] == [
        RAW_TLE_B,
        RAW_TLE_C,
        RAW_TLE_A,
    ]
    assert records[0]["id"] == newest_id
    assert records[0]["epoch_at"] == datetime(2026, 4, 26, 8, 20)
    assert_decoded_orbit(records[0], RAW_TLE_B)


def test_get_satellite_history_uses_newest_inserted_record_as_tiebreaker(db):
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle=RAW_TLE_A,
    )
    second_id = db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle=RAW_TLE_B,
    )

    records = db.get_satellite_history("2024-240A")

    assert records[0]["id"] == second_id
    assert [record["raw_tle"] for record in records] == [RAW_TLE_B, RAW_TLE_A]


def test_get_satellite_history_returns_empty_list_for_missing_satellite_table(db):
    assert db.get_satellite_history("2024-999A") == []


def test_get_satellite_history_migrates_existing_table_with_raw_tle(db):
    table_name = db.get_satellite_table_name("2024-240A")
    with db.engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE {table_name} ("
                "id INTEGER PRIMARY KEY, "
                "epoch_at DATETIME NOT NULL, "
                "inclination_deg FLOAT, "
                "perigee_km FLOAT, "
                "apogee_km FLOAT, "
                "eccentricity FLOAT"
                ")"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {table_name} "
                "(id, epoch_at, inclination_deg, perigee_km, apogee_km, eccentricity) "
                "VALUES (1, :epoch_at, 86.5, 1100.0, 1105.0, 0.00018)"
            ),
            {"epoch_at": "2026-04-26 08:00:00"},
        )

    records = db.get_satellite_history("2024-240A")

    assert records[0]["raw_tle"] is None
    assert records[0]["inclination_deg"] is None
    assert records[0]["perigee_km"] is None
    assert records[0]["apogee_km"] is None
    assert records[0]["eccentricity"] is None
    assert db.check_satellite_table_schema("2024-240A") is True


def test_get_satellite_history_rejects_empty_intl_designator(db):
    with pytest.raises(DatabaseConfigurationError, match="不能为空"):
        db.get_satellite_history("")


def test_get_satellite_history_wraps_database_errors(db):
    table_name = db.get_satellite_table_name("2024-240A")
    with db.engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"))

    with pytest.raises(DatabaseQueryError, match="历史轨道数据失败"):
        db.get_satellite_history("2024-240A")


def test_get_satellite_groups_returns_group_level_rows_with_related_names(db):
    manufacturer_id = db.create_manufacturer("五院", group_count=2, satellite_count=36)
    rocket_id = db.create_rocket("长征六号改", launch_count=2, satellite_count=36)
    first_group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2024-240",
        launch_time=datetime(2024, 12, 16, 10, 0),
        launch_site="太原",
        rocket_id=rocket_id,
        manufacturer_id=manufacturer_id,
        satellite_count=18,
        valid_satellite_count=17,
        invalid_satellite_count=1,
        launch_success=True,
        raw_tle=RAW_TLE_A,
    )
    db.create_satellite_group(
        name="低轨02组",
        intl_designator="2025-001",
        satellite_count=18,
    )
    db.add_group_satellite(
        first_group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-240A",
        raw_tle=RAW_TLE_A,
    )

    groups = db.get_satellite_groups()

    assert groups[0]["id"] == first_group_id
    assert groups[0]["name"] == "低轨01组"
    assert groups[0]["intl_designator"] == "2024-240"
    assert groups[0]["launch_time"] == datetime(2024, 12, 16, 10, 0)
    assert groups[0]["launch_site"] == "太原"
    assert groups[0]["rocket_id"] == rocket_id
    assert groups[0]["rocket_name"] == "长征六号改"
    assert groups[0]["manufacturer_id"] == manufacturer_id
    assert groups[0]["manufacturer_name"] == "五院"
    assert groups[0]["satellite_count"] == 18
    assert groups[0]["valid_satellite_count"] == 17
    assert groups[0]["invalid_satellite_count"] == 1
    assert groups[0]["launch_success"] is True
    assert groups[0]["raw_tle"] == RAW_TLE_A
    assert_decoded_orbit(groups[0], RAW_TLE_A)

    assert groups[1]["id"] == first_group_id + 1
    assert groups[1]["intl_designator"] == "2025-001"
    assert groups[1]["valid_satellite_count"] == 0
    assert groups[1]["invalid_satellite_count"] == 0
    assert groups[1]["launch_success"] is None
    assert groups[1]["raw_tle"] is None
    assert groups[1]["inclination_deg"] is None
    assert groups[1]["perigee_km"] is None
    assert groups[1]["apogee_km"] is None
    assert groups[1]["eccentricity"] is None
    assert "epoch_at" not in groups[0]


def test_get_satellite_groups_returns_empty_list_when_no_groups(db):
    assert db.get_satellite_groups() == []


def test_get_satellite_groups_wraps_database_errors():
    manager = DatabaseManager("sqlite3", ":memory:")

    with pytest.raises(DatabaseQueryError, match="卫星组总表信息失败"):
        manager.get_satellite_groups()


def test_get_satellite_group_detail_returns_group_and_member_satellites(db):
    manufacturer_id = db.create_manufacturer("五院", group_count=1, satellite_count=2)
    rocket_id = db.create_rocket("长征六号改", launch_count=1, satellite_count=2)
    group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2024-240",
        launch_time=datetime(2024, 12, 16, 10, 0),
        launch_site="太原",
        rocket_id=rocket_id,
        manufacturer_id=manufacturer_id,
        satellite_count=2,
        valid_satellite_count=1,
        invalid_satellite_count=1,
        launch_success=True,
        raw_tle=RAW_TLE_A,
    )
    first_satellite_id = db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-240A",
        raw_tle=RAW_TLE_B,
    )
    second_satellite_id = db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 5),
        intl_designator="2024-240B",
        status="失效",
        raw_tle=RAW_TLE_C,
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 9, 0),
        raw_tle=RAW_TLE_A,
    )

    detail = db.get_satellite_group_detail("2024-240")

    assert detail["id"] == group_id
    assert detail["launch_success"] is True
    assert detail["name"] == "低轨01组"
    assert detail["intl_designator"] == "2024-240"
    assert detail["launch_time"] == datetime(2024, 12, 16, 10, 0)
    assert detail["launch_site"] == "太原"
    assert detail["rocket_id"] == rocket_id
    assert detail["rocket_name"] == "长征六号改"
    assert detail["manufacturer_id"] == manufacturer_id
    assert detail["manufacturer_name"] == "五院"
    assert detail["satellite_count"] == 2
    assert detail["valid_satellite_count"] == 1
    assert detail["invalid_satellite_count"] == 1
    assert detail["raw_tle"] == RAW_TLE_A
    assert_decoded_orbit(detail, RAW_TLE_A)
    assert detail["satellites"][0]["id"] == first_satellite_id
    assert detail["satellites"][0]["intl_designator"] == "2024-240A"
    assert detail["satellites"][0]["status"] == "有效"
    assert detail["satellites"][0]["raw_tle"] == RAW_TLE_B
    assert_decoded_orbit(detail["satellites"][0], RAW_TLE_B)
    assert detail["satellites"][1]["id"] == second_satellite_id
    assert detail["satellites"][1]["intl_designator"] == "2024-240B"
    assert detail["satellites"][1]["status"] == "失效"
    assert detail["satellites"][1]["raw_tle"] == RAW_TLE_C
    assert_decoded_orbit(detail["satellites"][1], RAW_TLE_C)
    assert all("history" not in satellite for satellite in detail["satellites"])
    assert all(satellite["raw_tle"] != RAW_TLE_A for satellite in detail["satellites"])


def test_get_satellite_group_detail_returns_empty_satellites_without_group_table(db):
    group_id = db.create_satellite_group(
        name="低轨02组",
        intl_designator="2025-001",
        satellite_count=18,
    )

    detail = db.get_satellite_group_detail("2025-001")

    assert detail["id"] == group_id
    assert detail["intl_designator"] == "2025-001"
    assert detail["valid_satellite_count"] == 0
    assert detail["invalid_satellite_count"] == 0
    assert detail["satellites"] == []


def test_get_satellite_group_detail_returns_none_for_missing_group(db):
    assert db.get_satellite_group_detail("2099-001") is None


def test_get_satellite_group_detail_rejects_empty_intl_designator(db):
    with pytest.raises(DatabaseConfigurationError, match="不能为空"):
        db.get_satellite_group_detail("")


def test_get_satellite_group_detail_wraps_group_table_errors(db):
    group_id = db.create_satellite_group(
        name="低轨异常组",
        intl_designator="2099-001",
        satellite_count=1,
    )
    with db.engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE {db.get_group_table_name(group_id)} "
                "(id INTEGER PRIMARY KEY)"
            )
        )

    with pytest.raises(DatabaseQueryError, match="详情失败"):
        db.get_satellite_group_detail("2099-001")


def test_get_group_first_satellite_latest_tle_returns_first_satellite_tle(db):
    group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2024-240",
        satellite_count=2,
    )
    db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-240B",
    )
    db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-240A",
    )
    db.add_satellite_record(
        "2024-240B",
        epoch_at=datetime(2026, 4, 26, 9, 0),
        raw_tle="b latest tle",
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle="a older tle",
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 9, 0),
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 30),
        raw_tle="a latest non-null tle",
    )

    assert (
        db.get_group_first_satellite_latest_tle("2024-240")
        == "a latest non-null tle"
    )


def test_get_group_first_satellite_latest_tle_sorts_multi_letter_pieces(db):
    group_id = db.create_satellite_group(
        name="低轨多字母组",
        intl_designator="2024-241",
        satellite_count=2,
    )
    db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-241AA",
    )
    db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-241Z",
    )
    db.add_satellite_record(
        "2024-241AA",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle="aa tle",
    )
    db.add_satellite_record(
        "2024-241Z",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle="z tle",
    )

    assert db.get_group_first_satellite_latest_tle("2024-241") == "z tle"


def test_get_group_first_satellite_latest_tle_returns_none_for_missing_data(db):
    assert db.get_group_first_satellite_latest_tle("2099-001") is None

    group_without_table_id = db.create_satellite_group(
        name="无组表",
        intl_designator="2024-242",
    )
    assert group_without_table_id > 0
    assert db.get_group_first_satellite_latest_tle("2024-242") is None

    empty_group_id = db.create_satellite_group(
        name="空组表",
        intl_designator="2024-243",
    )
    db.create_group_table(empty_group_id)
    assert db.get_group_first_satellite_latest_tle("2024-243") is None

    missing_history_group_id = db.create_satellite_group(
        name="无历史表",
        intl_designator="2024-244",
    )
    db.add_group_satellite(
        missing_history_group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-244A",
    )
    assert db.get_group_first_satellite_latest_tle("2024-244") is None


def test_get_group_first_satellite_latest_tle_rejects_empty_intl_designator(db):
    with pytest.raises(DatabaseConfigurationError, match="不能为空"):
        db.get_group_first_satellite_latest_tle("")


def test_get_group_first_satellite_latest_tle_wraps_group_table_errors(db):
    group_id = db.create_satellite_group(
        name="低轨异常组",
        intl_designator="2099-002",
        satellite_count=1,
    )
    with db.engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE {db.get_group_table_name(group_id)} "
                "(id INTEGER PRIMARY KEY)"
            )
        )

    with pytest.raises(DatabaseQueryError, match="最新 TLE 失败"):
        db.get_group_first_satellite_latest_tle("2099-002")
