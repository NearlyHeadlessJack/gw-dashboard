from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from gw.database import (
    DatabaseConfigurationError,
    DatabaseManager,
    DatabaseSchemaError,
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

ORBIT_COLUMNS = {"inclination_deg", "perigee_km", "apogee_km", "eccentricity"}


def column_names(db, table_name):
    return {column["name"] for column in inspect(db.engine).get_columns(table_name)}


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


def test_initialize_database_creates_fixed_schema():
    manager = DatabaseManager("sqlite3", ":memory:")

    assert manager.check_schema() is False

    manager.initialize_database()

    inspector = inspect(manager.engine)
    assert manager.check_schema() is True
    assert {
        "metainfo",
        "manufacturers",
        "rockets",
        "satellite_groups",
    }.issubset(set(inspector.get_table_names()))
    metainfo_columns = {
        column["name"] for column in inspector.get_columns("metainfo")
    }
    assert "satellite_record_limit" in metainfo_columns
    rocket_columns = column_names(manager, "rockets")
    assert "serial_number" in rocket_columns
    satellite_group_columns = column_names(manager, "satellite_groups")
    assert "raw_tle" in satellite_group_columns
    assert "valid_satellite_count" in satellite_group_columns
    assert "invalid_satellite_count" in satellite_group_columns
    assert ORBIT_COLUMNS.isdisjoint(satellite_group_columns)


def test_initialize_database_raises_for_malformed_existing_table():
    manager = DatabaseManager("sqlite3", ":memory:")
    with manager.engine.begin() as conn:
        conn.execute(text("CREATE TABLE metainfo (id INTEGER PRIMARY KEY)"))

    with pytest.raises(DatabaseSchemaError, match="固定表结构"):
        manager.initialize_database()


def test_metainfo_crud_and_update_expiration(db):
    last_updated_at = datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc)

    assert db.is_update_expired(last_updated_at) is True

    db.set_metainfo(
        last_updated_at,
        valid_duration_seconds=3600,
        satellite_record_limit=500,
    )

    metainfo = db.get_metainfo()
    assert metainfo["valid_duration_seconds"] == 3600
    assert metainfo["satellite_record_limit"] == 500
    assert db.is_update_expired(last_updated_at + timedelta(seconds=3599)) is False
    assert db.is_update_expired(last_updated_at + timedelta(seconds=3600)) is True

    assert db.update_metainfo(
        valid_duration_seconds=7200,
        satellite_record_limit=1000,
    ) is True
    assert db.get_metainfo()["valid_duration_seconds"] == 7200
    assert db.get_metainfo()["satellite_record_limit"] == 1000

    assert db.delete_metainfo() is True
    assert db.get_metainfo() is None
    assert db.is_update_expired(last_updated_at) is True


def test_manufacturer_and_rocket_crud(db):
    manufacturer_id = db.create_manufacturer("五院", group_count=3, satellite_count=54)
    rocket_id = db.create_rocket(
        "长征五号乙",
        serial_number="Y7",
        launch_count=2,
        satellite_count=36,
    )

    assert db.get_manufacturer(manufacturer_id)["name"] == "五院"
    assert db.get_rocket(rocket_id)["name"] == "长征五号乙"
    assert db.get_rocket(rocket_id)["serial_number"] == "Y7"

    assert db.update_manufacturer(manufacturer_id, satellite_count=60) is True
    assert db.update_rocket(rocket_id, launch_count=3, serial_number="Y8") is True

    assert db.list_manufacturers()[0]["satellite_count"] == 60
    assert db.list_rockets()[0]["launch_count"] == 3
    assert db.list_rockets()[0]["serial_number"] == "Y8"

    assert db.delete_manufacturer(manufacturer_id) is True
    assert db.delete_rocket(rocket_id) is True
    assert db.get_manufacturer(manufacturer_id) is None
    assert db.get_rocket(rocket_id) is None


def test_satellite_group_total_table_crud(db):
    manufacturer_id = db.create_manufacturer("八院", group_count=1, satellite_count=18)
    rocket_id = db.create_rocket("长征六号改", launch_count=1, satellite_count=18)
    launch_time = datetime(2026, 1, 1, 12, 30)

    group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2024-240",
        launch_time=launch_time,
        launch_site="太原",
        rocket_id=rocket_id,
        manufacturer_id=manufacturer_id,
        satellite_count=18,
        valid_satellite_count=17,
        invalid_satellite_count=1,
        raw_tle=RAW_TLE_A,
    )

    group = db.get_satellite_group(group_id)
    assert group["intl_designator"] == "2024-240"
    assert group["manufacturer_id"] == manufacturer_id
    assert group["rocket_id"] == rocket_id
    assert group["raw_tle"] == RAW_TLE_A
    assert group["valid_satellite_count"] == 17
    assert group["invalid_satellite_count"] == 1
    assert_decoded_orbit(group, RAW_TLE_A)

    same_group = db.get_satellite_group_by_intl_designator("2024-240")
    assert same_group["id"] == group_id
    assert_decoded_orbit(same_group, RAW_TLE_A)

    assert db.update_satellite_group(
        group_id,
        satellite_count=20,
        valid_satellite_count=19,
        invalid_satellite_count=1,
        raw_tle=RAW_TLE_B,
    ) is True
    assert db.list_satellite_groups()[0]["satellite_count"] == 20
    assert db.list_satellite_groups()[0]["valid_satellite_count"] == 19
    assert db.list_satellite_groups()[0]["invalid_satellite_count"] == 1
    assert db.list_satellite_groups()[0]["raw_tle"] == RAW_TLE_B

    assert db.delete_satellite_group(group_id) is True
    assert db.get_satellite_group(group_id) is None


def test_satellite_group_references_manufacturer_and_rocket(db):
    with pytest.raises(IntegrityError):
        db.create_satellite_group(
            name="低轨异常组",
            intl_designator="2099-001",
            rocket_id=999,
            manufacturer_id=999,
        )


def test_group_table_crud(db):
    table_name = db.create_group_table(1)
    epoch_at = datetime(2026, 4, 26, 8, 15)

    assert table_name == "satellite_group_1"
    assert db.check_group_table_schema(1) is True
    assert "status" in column_names(db, table_name)
    assert "raw_tle" in column_names(db, table_name)
    assert ORBIT_COLUMNS.isdisjoint(column_names(db, table_name))

    record_id = db.add_group_satellite(
        1,
        epoch_at=epoch_at,
        intl_designator="2024-240A",
        raw_tle=RAW_TLE_A,
    )

    record = db.get_group_satellite(1, record_id)
    assert record["intl_designator"] == "2024-240A"
    assert record["status"] == "有效"
    assert record["raw_tle"] == RAW_TLE_A
    assert_decoded_orbit(record, RAW_TLE_A)

    assert db.update_group_satellite(
        1,
        record_id,
        status="失效",
        raw_tle=RAW_TLE_B,
    ) is True
    assert db.list_group_satellites(1)[0]["status"] == "失效"
    assert db.list_group_satellites(1)[0]["raw_tle"] == RAW_TLE_B
    assert_decoded_orbit(db.list_group_satellites(1)[0], RAW_TLE_B)

    with pytest.raises(DatabaseConfigurationError, match="状态"):
        db.update_group_satellite(1, record_id, status="未知")

    assert db.delete_group_satellite(1, record_id) is True
    assert db.list_group_satellites(1) == []

    assert db.get_group_satellite(999, 1) is None
    assert db.update_group_satellite(999, 1, raw_tle=RAW_TLE_A) is False
    assert db.delete_group_satellite(999, 1) is False


def test_satellite_history_table_crud(db):
    table_name = db.create_satellite_table("2024-240A")
    epoch_at = datetime(2026, 4, 26, 8, 30)

    assert table_name.startswith("satellite_2024_240a_")
    assert db.check_satellite_table_schema("2024-240A") is True
    columns = column_names(db, table_name)
    assert "raw_tle" in columns
    assert ORBIT_COLUMNS.isdisjoint(columns)

    record_id = db.add_satellite_record(
        "2024-240A",
        epoch_at=epoch_at,
        raw_tle=RAW_TLE_A,
    )

    record = db.get_satellite_record("2024-240A", record_id)
    assert record["raw_tle"] == RAW_TLE_A
    assert_decoded_orbit(record, RAW_TLE_A)

    assert db.update_satellite_record(
        "2024-240A",
        record_id,
        raw_tle=RAW_TLE_B,
    )
    updated_record = db.list_satellite_records("2024-240A")[0]
    assert updated_record["raw_tle"] == RAW_TLE_B
    assert_decoded_orbit(updated_record, RAW_TLE_B)

    with pytest.raises(DatabaseConfigurationError, match="不支持的字段"):
        db.update_satellite_record("2024-240A", record_id, eccentricity=0.00021)

    assert db.delete_satellite_record("2024-240A", record_id)
    assert db.list_satellite_records("2024-240A") == []

    assert db.get_satellite_record("2024-999A", 1) is None
    assert db.update_satellite_record("2024-999A", 1, raw_tle=RAW_TLE_A) is False
    assert db.delete_satellite_record("2024-999A", 1) is False


def test_create_satellite_table_migrates_existing_history_table_with_raw_tle(db):
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

    assert db.check_satellite_table_schema("2024-240A") is False

    assert db.create_satellite_table("2024-240A") == table_name

    assert db.check_satellite_table_schema("2024-240A") is True
    assert "raw_tle" in column_names(db, table_name)


def test_satellite_history_limit_keeps_newest_epoch_records(db):
    db.set_metainfo(
        datetime(2026, 4, 26, 8, 0),
        valid_duration_seconds=3600,
        satellite_record_limit=2,
    )
    newest_id = db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 20),
        raw_tle=RAW_TLE_A,
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle=RAW_TLE_B,
    )
    older_kept_id = db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 10),
        raw_tle=RAW_TLE_C,
    )

    records = db.list_satellite_records("2024-240A")
    assert len(records) == 2
    assert {record["raw_tle"] for record in records} == {RAW_TLE_A, RAW_TLE_C}

    db.update_metainfo(satellite_record_limit=1)
    assert db.update_satellite_record(
        "2024-240A",
        older_kept_id,
        raw_tle=RAW_TLE_C,
    )

    records = db.list_satellite_records("2024-240A")
    assert len(records) == 1
    assert records[0]["id"] == newest_id
    assert records[0]["raw_tle"] == RAW_TLE_A


def test_invalid_fields_and_dynamic_table_names_raise(db):
    rocket_id = db.create_rocket("长征八号")

    with pytest.raises(DatabaseConfigurationError, match="不支持的字段"):
        db.update_rocket(rocket_id, unknown_field=1)

    with pytest.raises(DatabaseConfigurationError, match="正整数"):
        db.get_group_table_name(0)

    with pytest.raises(DatabaseConfigurationError, match="不能为空"):
        db.get_satellite_table_name("")

    with pytest.raises(DatabaseConfigurationError, match="不能为负数"):
        db.set_metainfo(datetime.now(timezone.utc), -1)

    with pytest.raises(DatabaseConfigurationError, match="上限"):
        db.set_metainfo(datetime.now(timezone.utc), 3600, satellite_record_limit=0)

    with pytest.raises(DatabaseConfigurationError, match="上限"):
        db.update_metainfo(satellite_record_limit=-1)
