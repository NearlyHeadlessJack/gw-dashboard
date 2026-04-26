"""数据库连接管理。

负责根据配置创建 SQLAlchemy engine、测试数据库连接、初始化表结构，
并提供项目当前需要的基础 CRUD 操作。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import (
    URL,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    inspect,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import sqltypes
from sqlalchemy.sql.type_api import TypeEngine

from gw.utils.tle import TleParseError, parse_tle


ConnectionInfo = str | Path | Mapping[str, Any]
RowData = dict[str, Any]

FIXED_METADATA = MetaData()

METAINFO_TABLE = Table(
    "metainfo",
    FIXED_METADATA,
    Column("id", Integer, primary_key=True),
    Column("last_updated_at", DateTime(timezone=True), nullable=True),
    Column("valid_duration_seconds", Integer, nullable=False),
    Column("satellite_record_limit", Integer, nullable=True),
)

MANUFACTURERS_TABLE = Table(
    "manufacturers",
    FIXED_METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False, unique=True),
    Column("group_count", Integer, nullable=False, default=0),
    Column("satellite_count", Integer, nullable=False, default=0),
)

ROCKETS_TABLE = Table(
    "rockets",
    FIXED_METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("serial_number", String(64), nullable=True),
    Column("launch_count", Integer, nullable=False, default=0),
    Column("satellite_count", Integer, nullable=False, default=0),
)

SATELLITE_GROUPS_TABLE = Table(
    "satellite_groups",
    FIXED_METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("intl_designator", String(64), nullable=False, unique=True),
    Column("launch_time", DateTime(timezone=True), nullable=True),
    Column("launch_site", String(255), nullable=True),
    Column("rocket_id", Integer, ForeignKey("rockets.id"), nullable=True),
    Column("manufacturer_id", Integer, ForeignKey("manufacturers.id"), nullable=True),
    Column("satellite_count", Integer, nullable=False, default=0),
    Column("valid_satellite_count", Integer, nullable=False, default=0),
    Column("invalid_satellite_count", Integer, nullable=False, default=0),
    Column("raw_tle", Text, nullable=True),
)

FIXED_SCHEMA: dict[str, dict[str, type[TypeEngine]]] = {
    "metainfo": {
        "id": Integer,
        "last_updated_at": DateTime,
        "valid_duration_seconds": Integer,
        "satellite_record_limit": Integer,
    },
    "manufacturers": {
        "id": Integer,
        "name": String,
        "group_count": Integer,
        "satellite_count": Integer,
    },
    "rockets": {
        "id": Integer,
        "name": String,
        "serial_number": String,
        "launch_count": Integer,
        "satellite_count": Integer,
    },
    "satellite_groups": {
        "id": Integer,
        "name": String,
        "intl_designator": String,
        "launch_time": DateTime,
        "launch_site": String,
        "rocket_id": Integer,
        "manufacturer_id": Integer,
        "satellite_count": Integer,
        "valid_satellite_count": Integer,
        "invalid_satellite_count": Integer,
        "raw_tle": Text,
    },
}

GROUP_TABLE_SCHEMA: dict[str, type[TypeEngine]] = {
    "id": Integer,
    "epoch_at": DateTime,
    "intl_designator": String,
    "status": String,
    "raw_tle": Text,
}

SATELLITE_TABLE_SCHEMA: dict[str, type[TypeEngine]] = {
    "id": Integer,
    "epoch_at": DateTime,
    "raw_tle": Text,
}


class DatabaseConfigurationError(ValueError):
    """数据库连接配置无效。"""


class DatabaseSchemaError(RuntimeError):
    """数据库表结构不符合项目预期。"""


class DatabaseQueryError(RuntimeError):
    """数据库查询失败。"""


class DatabaseManager:
    """统一管理数据库连接创建和连通性测试。"""

    _TYPE_ALIASES = {
        "sqlite": "sqlite3",
        "sqlite3": "sqlite3",
        "mysql": "mysql",
        "pgsql": "pgsql",
        "postgres": "pgsql",
        "postgresql": "pgsql",
    }

    def __init__(self, db_type: str, connection: ConnectionInfo):
        self.db_type = self._normalize_db_type(db_type)
        self.connection = connection
        self.database_url = self._build_database_url(self.db_type, connection)
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True)
        if self.db_type == "sqlite3":
            self._enable_sqlite_foreign_keys()

    def test_connection(self) -> bool:
        """执行轻量查询，返回数据库连接是否可用。"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def initialize_database(self) -> None:
        """创建固定表并检查表结构。"""
        FIXED_METADATA.create_all(self.engine, checkfirst=True)
        self._migrate_fixed_schema()
        if not self.check_schema():
            raise DatabaseSchemaError("数据库固定表结构不符合预期")

    def check_schema(self) -> bool:
        """检查固定表是否存在且包含预期列和类型。"""
        return self._check_schema(FIXED_SCHEMA)

    def set_metainfo(
        self,
        last_updated_at: datetime | None,
        valid_duration_seconds: int,
        satellite_record_limit: int | None = None,
    ) -> None:
        """写入或替换唯一一行更新元信息。"""
        if valid_duration_seconds < 0:
            raise DatabaseConfigurationError("数据有效期不能为负数")
        self._validate_satellite_record_limit(satellite_record_limit)

        values = {
            "last_updated_at": last_updated_at,
            "valid_duration_seconds": valid_duration_seconds,
            "satellite_record_limit": satellite_record_limit,
        }
        with self.engine.begin() as conn:
            result = conn.execute(
                update(METAINFO_TABLE)
                .where(METAINFO_TABLE.c.id == 1)
                .values(**values)
            )
            if result.rowcount == 0:
                conn.execute(insert(METAINFO_TABLE).values(id=1, **values))

    def get_metainfo(self) -> RowData | None:
        """读取更新元信息。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                select(METAINFO_TABLE).where(METAINFO_TABLE.c.id == 1)
            ).first()
        return self._row_to_dict(row)

    def update_metainfo(self, **fields: Any) -> bool:
        """更新元信息字段。"""
        values = self._filter_values(
            METAINFO_TABLE,
            fields,
            allowed=(
                "last_updated_at",
                "valid_duration_seconds",
                "satellite_record_limit",
            ),
        )
        if "valid_duration_seconds" in values and values["valid_duration_seconds"] < 0:
            raise DatabaseConfigurationError("数据有效期不能为负数")
        if "satellite_record_limit" in values:
            self._validate_satellite_record_limit(values["satellite_record_limit"])
        return self._update_by_id(METAINFO_TABLE, 1, values)

    def delete_metainfo(self) -> bool:
        """删除更新元信息。"""
        return self._delete_by_id(METAINFO_TABLE, 1)

    def is_update_expired(self, now: datetime | None = None) -> bool:
        """检查数据是否已超过有效期；没有元信息时视为已过期。"""
        metainfo = self.get_metainfo()
        if not metainfo or metainfo["last_updated_at"] is None:
            return True

        current_time = self._to_utc_naive(now or datetime.now(timezone.utc))
        last_updated_at = self._to_utc_naive(metainfo["last_updated_at"])
        valid_until = last_updated_at + timedelta(
            seconds=metainfo["valid_duration_seconds"]
        )
        return current_time >= valid_until

    def create_manufacturer(
        self,
        name: str,
        group_count: int = 0,
        satellite_count: int = 0,
    ) -> int:
        """新增研制单位。"""
        return self._insert_row(
            MANUFACTURERS_TABLE,
            {
                "name": name,
                "group_count": group_count,
                "satellite_count": satellite_count,
            },
        )

    def get_manufacturer(self, manufacturer_id: int) -> RowData | None:
        """按 ID 查询研制单位。"""
        return self._get_by_id(MANUFACTURERS_TABLE, manufacturer_id)

    def list_manufacturers(self) -> list[RowData]:
        """查询全部研制单位。"""
        return self._list_rows(MANUFACTURERS_TABLE)

    def update_manufacturer(self, manufacturer_id: int, **fields: Any) -> bool:
        """更新研制单位。"""
        values = self._filter_values(
            MANUFACTURERS_TABLE,
            fields,
            allowed=("name", "group_count", "satellite_count"),
        )
        return self._update_by_id(MANUFACTURERS_TABLE, manufacturer_id, values)

    def delete_manufacturer(self, manufacturer_id: int) -> bool:
        """删除研制单位。"""
        return self._delete_by_id(MANUFACTURERS_TABLE, manufacturer_id)

    def create_rocket(
        self,
        name: str,
        serial_number: str | None = None,
        launch_count: int = 0,
        satellite_count: int = 0,
    ) -> int:
        """新增火箭。"""
        return self._insert_row(
            ROCKETS_TABLE,
            {
                "name": name,
                "serial_number": serial_number,
                "launch_count": launch_count,
                "satellite_count": satellite_count,
            },
        )

    def get_rocket(self, rocket_id: int) -> RowData | None:
        """按 ID 查询火箭。"""
        return self._get_by_id(ROCKETS_TABLE, rocket_id)

    def list_rockets(self) -> list[RowData]:
        """查询全部火箭。"""
        return self._list_rows(ROCKETS_TABLE)

    def update_rocket(self, rocket_id: int, **fields: Any) -> bool:
        """更新火箭。"""
        values = self._filter_values(
            ROCKETS_TABLE,
            fields,
            allowed=("name", "serial_number", "launch_count", "satellite_count"),
        )
        return self._update_by_id(ROCKETS_TABLE, rocket_id, values)

    def delete_rocket(self, rocket_id: int) -> bool:
        """删除火箭。"""
        return self._delete_by_id(ROCKETS_TABLE, rocket_id)

    def create_satellite_group(
        self,
        *,
        name: str,
        intl_designator: str,
        launch_time: datetime | None = None,
        launch_site: str | None = None,
        rocket_id: int | None = None,
        manufacturer_id: int | None = None,
        satellite_count: int = 0,
        valid_satellite_count: int = 0,
        invalid_satellite_count: int = 0,
        raw_tle: str | None = None,
    ) -> int:
        """新增星网卫星组总表记录。"""
        return self._insert_row(
            SATELLITE_GROUPS_TABLE,
            {
                "name": name,
                "intl_designator": intl_designator,
                "launch_time": launch_time,
                "launch_site": launch_site,
                "rocket_id": rocket_id,
                "manufacturer_id": manufacturer_id,
                "satellite_count": satellite_count,
                "valid_satellite_count": valid_satellite_count,
                "invalid_satellite_count": invalid_satellite_count,
                "raw_tle": raw_tle,
            },
        )

    def get_satellite_group(self, group_id: int) -> RowData | None:
        """按 ID 查询卫星组。"""
        return self._enrich_orbit_row(
            self._get_by_id(SATELLITE_GROUPS_TABLE, group_id)
        )

    def get_satellite_group_by_intl_designator(
        self,
        intl_designator: str,
    ) -> RowData | None:
        """按国际识别号查询卫星组。"""
        with self.engine.connect() as conn:
            row = conn.execute(
                select(SATELLITE_GROUPS_TABLE).where(
                    SATELLITE_GROUPS_TABLE.c.intl_designator == intl_designator
                )
            ).first()
        return self._enrich_orbit_row(self._row_to_dict(row))

    def list_satellite_groups(self) -> list[RowData]:
        """查询全部卫星组。"""
        return self._enrich_orbit_rows(self._list_rows(SATELLITE_GROUPS_TABLE))

    def get_satellite_groups(self) -> list[RowData]:
        """供 web 查询：返回以组为单位的星网卫星总表信息。"""
        try:
            query = (
                select(
                    SATELLITE_GROUPS_TABLE.c.id,
                    SATELLITE_GROUPS_TABLE.c.name,
                    SATELLITE_GROUPS_TABLE.c.intl_designator,
                    SATELLITE_GROUPS_TABLE.c.launch_time,
                    SATELLITE_GROUPS_TABLE.c.launch_site,
                    SATELLITE_GROUPS_TABLE.c.rocket_id,
                    ROCKETS_TABLE.c.name.label("rocket_name"),
                    ROCKETS_TABLE.c.serial_number.label("rocket_serial_number"),
                    SATELLITE_GROUPS_TABLE.c.manufacturer_id,
                    MANUFACTURERS_TABLE.c.name.label("manufacturer_name"),
                    SATELLITE_GROUPS_TABLE.c.satellite_count,
                    SATELLITE_GROUPS_TABLE.c.valid_satellite_count,
                    SATELLITE_GROUPS_TABLE.c.invalid_satellite_count,
                    SATELLITE_GROUPS_TABLE.c.raw_tle,
                )
                .select_from(
                    SATELLITE_GROUPS_TABLE.outerjoin(
                        ROCKETS_TABLE,
                        SATELLITE_GROUPS_TABLE.c.rocket_id == ROCKETS_TABLE.c.id,
                    ).outerjoin(
                        MANUFACTURERS_TABLE,
                        SATELLITE_GROUPS_TABLE.c.manufacturer_id
                        == MANUFACTURERS_TABLE.c.id,
                    )
                )
                .order_by(SATELLITE_GROUPS_TABLE.c.id)
            )
            with self.engine.connect() as conn:
                rows = conn.execute(query).all()
            return self._enrich_orbit_rows([dict(row._mapping) for row in rows])
        except SQLAlchemyError as exc:
            raise DatabaseQueryError("查询卫星组总表信息失败") from exc

    def get_satellite_group_detail(self, intl_designator: str) -> RowData | None:
        """供 web 查询：按组国际识别号返回组信息和组内卫星基础信息。"""
        if str(intl_designator).strip() == "":
            raise DatabaseConfigurationError("组国际识别号不能为空")

        try:
            query = (
                select(
                    SATELLITE_GROUPS_TABLE.c.id,
                    SATELLITE_GROUPS_TABLE.c.name,
                    SATELLITE_GROUPS_TABLE.c.intl_designator,
                    SATELLITE_GROUPS_TABLE.c.launch_time,
                    SATELLITE_GROUPS_TABLE.c.launch_site,
                    SATELLITE_GROUPS_TABLE.c.rocket_id,
                    ROCKETS_TABLE.c.name.label("rocket_name"),
                    ROCKETS_TABLE.c.serial_number.label("rocket_serial_number"),
                    SATELLITE_GROUPS_TABLE.c.manufacturer_id,
                    MANUFACTURERS_TABLE.c.name.label("manufacturer_name"),
                    SATELLITE_GROUPS_TABLE.c.satellite_count,
                    SATELLITE_GROUPS_TABLE.c.valid_satellite_count,
                    SATELLITE_GROUPS_TABLE.c.invalid_satellite_count,
                    SATELLITE_GROUPS_TABLE.c.raw_tle,
                )
                .select_from(
                    SATELLITE_GROUPS_TABLE.outerjoin(
                        ROCKETS_TABLE,
                        SATELLITE_GROUPS_TABLE.c.rocket_id == ROCKETS_TABLE.c.id,
                    ).outerjoin(
                        MANUFACTURERS_TABLE,
                        SATELLITE_GROUPS_TABLE.c.manufacturer_id
                        == MANUFACTURERS_TABLE.c.id,
                    )
                )
                .where(SATELLITE_GROUPS_TABLE.c.intl_designator == intl_designator)
            )
            with self.engine.connect() as conn:
                group_row = conn.execute(query).first()
                if group_row is None:
                    return None

                group = self._enrich_orbit_row(dict(group_row._mapping))
                table_name = self.get_group_table_name(group["id"])
                if not inspect(conn).has_table(table_name):
                    group["satellites"] = []
                    return group

                self._migrate_group_table_schema(group["id"])
                group_table = self._group_table(group["id"])
                satellite_rows = conn.execute(
                    select(group_table).order_by(group_table.c.id)
                ).all()
                group["satellites"] = self._enrich_orbit_rows(
                    [dict(row._mapping) for row in satellite_rows]
                )
                return group
        except SQLAlchemyError as exc:
            raise DatabaseQueryError(
                f"查询卫星组 {intl_designator!r} 详情失败"
            ) from exc

    def get_group_first_satellite_latest_tle(
        self,
        intl_designator: str,
    ) -> str | None:
        """供 web 查询：返回某组第一颗卫星最新的原始 TLE。"""
        if str(intl_designator).strip() == "":
            raise DatabaseConfigurationError("组国际识别号不能为空")

        try:
            with self.engine.connect() as conn:
                group_row = conn.execute(
                    select(SATELLITE_GROUPS_TABLE.c.id).where(
                        SATELLITE_GROUPS_TABLE.c.intl_designator == intl_designator
                    )
                ).first()
                if group_row is None:
                    return None

                group_id = int(group_row._mapping["id"])
                group_table_name = self.get_group_table_name(group_id)
                if not inspect(conn).has_table(group_table_name):
                    return None

                group_table = self._group_table(group_id)
                satellite_rows = conn.execute(
                    select(group_table.c.intl_designator)
                ).all()
                satellite_intl_designators = [
                    str(row._mapping["intl_designator"])
                    for row in satellite_rows
                    if row._mapping["intl_designator"]
                ]
                if not satellite_intl_designators:
                    return None

            first_satellite_intl_designator = min(
                satellite_intl_designators,
                key=self._intl_designator_sort_key,
            )
            table_name = self.get_satellite_table_name(
                first_satellite_intl_designator
            )
            if not inspect(self.engine).has_table(table_name):
                return None
            self._migrate_satellite_table_schema(first_satellite_intl_designator)

            satellite_table = self._satellite_table(first_satellite_intl_designator)
            with self.engine.connect() as conn:
                latest_tle_row = conn.execute(
                    select(satellite_table.c.raw_tle)
                    .where(satellite_table.c.raw_tle.is_not(None))
                    .order_by(
                        satellite_table.c.epoch_at.desc(),
                        satellite_table.c.id.desc(),
                    )
                ).first()
            if latest_tle_row is None:
                return None
            return latest_tle_row._mapping["raw_tle"]
        except DatabaseConfigurationError:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseQueryError(
                f"查询卫星组 {intl_designator!r} 第一颗卫星最新 TLE 失败"
            ) from exc

    def update_satellite_group(self, group_id: int, **fields: Any) -> bool:
        """更新卫星组总表记录。"""
        values = self._filter_values(
            SATELLITE_GROUPS_TABLE,
            fields,
            allowed=(
                "name",
                "intl_designator",
                "launch_time",
                "launch_site",
                "rocket_id",
                "manufacturer_id",
                "satellite_count",
                "valid_satellite_count",
                "invalid_satellite_count",
                "raw_tle",
            ),
        )
        return self._update_by_id(SATELLITE_GROUPS_TABLE, group_id, values)

    def delete_satellite_group(self, group_id: int) -> bool:
        """删除卫星组总表记录。"""
        return self._delete_by_id(SATELLITE_GROUPS_TABLE, group_id)

    def get_group_table_name(self, group_id: int) -> str:
        """返回某个卫星组对应的动态组表名。"""
        if group_id <= 0:
            raise DatabaseConfigurationError("卫星组 ID 必须是正整数")
        return f"satellite_group_{group_id}"

    def create_group_table(self, group_id: int) -> str:
        """创建某个卫星组的动态组表。"""
        table = self._group_table(group_id)
        table.create(self.engine, checkfirst=True)
        self._migrate_group_table_schema(group_id)
        if not self.check_group_table_schema(group_id):
            raise DatabaseSchemaError(f"{table.name} 表结构不符合预期")
        return table.name

    def check_group_table_schema(self, group_id: int) -> bool:
        """检查某个动态组表结构。"""
        return self._check_schema(
            {self.get_group_table_name(group_id): GROUP_TABLE_SCHEMA}
        )

    def drop_group_table(self, group_id: int) -> None:
        """删除某个动态组表。"""
        self._group_table(group_id).drop(self.engine, checkfirst=True)

    def add_group_satellite(
        self,
        group_id: int,
        *,
        epoch_at: datetime,
        intl_designator: str,
        status: str = "有效",
        raw_tle: str | None = None,
    ) -> int:
        """向动态组表新增单颗卫星当前数据。"""
        table = self._group_table(group_id)
        self.create_group_table(group_id)
        return self._insert_row(
            table,
            {
                "epoch_at": epoch_at,
                "intl_designator": intl_designator,
                "status": self._normalize_satellite_status(status),
                "raw_tle": raw_tle,
            },
        )

    def get_group_satellite(self, group_id: int, record_id: int) -> RowData | None:
        """查询动态组表中的某条卫星记录。"""
        table_name = self.get_group_table_name(group_id)
        if not inspect(self.engine).has_table(table_name):
            return None
        self._migrate_group_table_schema(group_id)
        return self._enrich_orbit_row(
            self._get_by_id(self._group_table(group_id), record_id)
        )

    def list_group_satellites(self, group_id: int) -> list[RowData]:
        """查询动态组表中的全部卫星记录。"""
        table_name = self.get_group_table_name(group_id)
        if not inspect(self.engine).has_table(table_name):
            return []
        self._migrate_group_table_schema(group_id)
        return self._enrich_orbit_rows(
            self._list_rows(self._group_table(group_id))
        )

    def update_group_satellite(
        self,
        group_id: int,
        record_id: int,
        **fields: Any,
    ) -> bool:
        """更新动态组表中的某条卫星记录。"""
        table_name = self.get_group_table_name(group_id)
        if not inspect(self.engine).has_table(table_name):
            return False
        self._migrate_group_table_schema(group_id)
        field_values = dict(fields)
        if "status" in field_values:
            field_values["status"] = self._normalize_satellite_status(
                field_values["status"]
            )
        values = self._filter_values(
            self._group_table(group_id),
            field_values,
            allowed=(
                "epoch_at",
                "intl_designator",
                "status",
                "raw_tle",
            ),
        )
        return self._update_by_id(self._group_table(group_id), record_id, values)

    def delete_group_satellite(self, group_id: int, record_id: int) -> bool:
        """删除动态组表中的某条卫星记录。"""
        table_name = self.get_group_table_name(group_id)
        if not inspect(self.engine).has_table(table_name):
            return False
        return self._delete_by_id(self._group_table(group_id), record_id)

    def get_satellite_table_name(self, intl_designator: str) -> str:
        """返回单颗卫星历史表表名。"""
        return self._safe_table_name("satellite", intl_designator)

    def create_satellite_table(self, intl_designator: str) -> str:
        """创建单颗卫星历史表。"""
        table = self._satellite_table(intl_designator)
        table.create(self.engine, checkfirst=True)
        self._migrate_satellite_table_schema(intl_designator)
        if not self.check_satellite_table_schema(intl_designator):
            raise DatabaseSchemaError(f"{table.name} 表结构不符合预期")
        return table.name

    def check_satellite_table_schema(self, intl_designator: str) -> bool:
        """检查单颗卫星历史表结构。"""
        return self._check_schema(
            {self.get_satellite_table_name(intl_designator): SATELLITE_TABLE_SCHEMA}
        )

    def drop_satellite_table(self, intl_designator: str) -> None:
        """删除单颗卫星历史表。"""
        self._satellite_table(intl_designator).drop(self.engine, checkfirst=True)

    def add_satellite_record(
        self,
        intl_designator: str,
        *,
        epoch_at: datetime,
        raw_tle: str | None = None,
    ) -> int:
        """向单颗卫星历史表新增轨道记录。"""
        table = self._satellite_table(intl_designator)
        self.create_satellite_table(intl_designator)
        record_id = self._insert_row(
            table,
            {
                "epoch_at": epoch_at,
                "raw_tle": raw_tle,
            },
        )
        self._trim_satellite_records(table)
        return record_id

    def get_satellite_record(
        self,
        intl_designator: str,
        record_id: int,
    ) -> RowData | None:
        """查询单颗卫星历史表中的某条记录。"""
        table_name = self.get_satellite_table_name(intl_designator)
        if not inspect(self.engine).has_table(table_name):
            return None
        self._migrate_satellite_table_schema(intl_designator)
        return self._enrich_orbit_row(
            self._get_by_id(self._satellite_table(intl_designator), record_id)
        )

    def list_satellite_records(self, intl_designator: str) -> list[RowData]:
        """查询单颗卫星历史表中的全部记录。"""
        table_name = self.get_satellite_table_name(intl_designator)
        if not inspect(self.engine).has_table(table_name):
            return []
        self._migrate_satellite_table_schema(intl_designator)
        return self._enrich_orbit_rows(
            self._list_rows(self._satellite_table(intl_designator))
        )

    def get_satellite_history(self, intl_designator: str) -> list[RowData]:
        """供 web 查询：按历元从新到旧返回单颗卫星全部历史数据。"""
        try:
            table_name = self.get_satellite_table_name(intl_designator)
            if not inspect(self.engine).has_table(table_name):
                return []
            self._migrate_satellite_table_schema(intl_designator)

            table = self._satellite_table(intl_designator)
            with self.engine.connect() as conn:
                rows = conn.execute(
                    select(table).order_by(
                        table.c.epoch_at.desc(),
                        table.c.id.desc(),
                    )
                ).all()
            return self._enrich_orbit_rows([dict(row._mapping) for row in rows])
        except DatabaseConfigurationError:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseQueryError(
                f"查询卫星 {intl_designator!r} 历史轨道数据失败"
            ) from exc

    def update_satellite_record(
        self,
        intl_designator: str,
        record_id: int,
        **fields: Any,
    ) -> bool:
        """更新单颗卫星历史表中的某条记录。"""
        table_name = self.get_satellite_table_name(intl_designator)
        if not inspect(self.engine).has_table(table_name):
            return False
        self._migrate_satellite_table_schema(intl_designator)
        values = self._filter_values(
            self._satellite_table(intl_designator),
            fields,
            allowed=(
                "epoch_at",
                "raw_tle",
            ),
        )
        updated = self._update_by_id(
            self._satellite_table(intl_designator),
            record_id,
            values,
        )
        if updated:
            self._trim_satellite_records(self._satellite_table(intl_designator))
        return updated

    def delete_satellite_record(self, intl_designator: str, record_id: int) -> bool:
        """删除单颗卫星历史表中的某条记录。"""
        table_name = self.get_satellite_table_name(intl_designator)
        if not inspect(self.engine).has_table(table_name):
            return False
        return self._delete_by_id(self._satellite_table(intl_designator), record_id)

    @classmethod
    def _normalize_db_type(cls, db_type: str) -> str:
        normalized = db_type.strip().lower()
        if normalized not in cls._TYPE_ALIASES:
            supported = ", ".join(sorted(cls._TYPE_ALIASES))
            raise DatabaseConfigurationError(
                f"不支持的数据库类型: {db_type!r}，支持: {supported}"
            )
        return cls._TYPE_ALIASES[normalized]

    @classmethod
    def _build_database_url(cls, db_type: str, connection: ConnectionInfo) -> str | URL:
        if db_type == "sqlite3":
            return cls._build_sqlite_url(connection)
        if isinstance(connection, str) and "://" in connection:
            return connection
        if not isinstance(connection, Mapping):
            raise DatabaseConfigurationError(
                "mysql/pgsql 连接信息必须是 SQLAlchemy URL 字符串或 dict"
            )
        return cls._build_server_url(db_type, connection)

    @staticmethod
    def _build_sqlite_url(connection: ConnectionInfo) -> URL | str:
        if isinstance(connection, Mapping):
            database = connection.get("database") or connection.get("path")
        else:
            database = connection

        if database is None or str(database).strip() == "":
            raise DatabaseConfigurationError("sqlite3 需要提供数据库文件位置")

        database_path = str(database)
        if database_path == ":memory:":
            return "sqlite+pysqlite:///:memory:"

        return URL.create(
            "sqlite+pysqlite",
            database=str(Path(database_path).expanduser()),
        )

    @classmethod
    def _build_server_url(cls, db_type: str, connection: Mapping[str, Any]) -> URL:
        username = cls._first_present(connection, "username", "user")
        database = cls._first_present(connection, "database", "dbname", "db")
        host = str(connection.get("host", "localhost"))
        password = connection.get("password")
        port = connection.get("port")

        if db_type == "mysql":
            drivername = str(connection.get("driver", "mysql+pymysql"))
            default_port = 3306
        else:
            drivername = str(connection.get("driver", "postgresql+psycopg"))
            default_port = 5432

        return URL.create(
            drivername=drivername,
            username=str(username),
            password=None if password is None else str(password),
            host=host,
            port=int(port) if port is not None else default_port,
            database=str(database),
        )

    @staticmethod
    def _first_present(connection: Mapping[str, Any], *keys: str) -> Any:
        for key in keys:
            value = connection.get(key)
            if value is not None and str(value).strip() != "":
                return value
        joined_keys = "/".join(keys)
        raise DatabaseConfigurationError(f"缺少数据库连接字段: {joined_keys}")

    def _enable_sqlite_foreign_keys(self) -> None:
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    def _check_schema(
        self,
        expected_schema: Mapping[str, Mapping[str, type[TypeEngine]]],
    ) -> bool:
        inspector = inspect(self.engine)
        for table_name, expected_columns in expected_schema.items():
            if not inspector.has_table(table_name):
                return False
            columns = {
                column["name"]: column["type"]
                for column in inspector.get_columns(table_name)
            }
            for column_name, expected_type in expected_columns.items():
                actual_type = columns.get(column_name)
                if actual_type is None:
                    return False
                if not self._type_matches(actual_type, expected_type):
                    return False
        return True

    @staticmethod
    def _type_matches(actual_type: TypeEngine, expected_type: type[TypeEngine]) -> bool:
        if issubclass(expected_type, Integer):
            return isinstance(actual_type, sqltypes.Integer)
        if issubclass(expected_type, Float):
            return isinstance(actual_type, (sqltypes.Float, sqltypes.Numeric))
        if issubclass(expected_type, DateTime):
            return isinstance(actual_type, sqltypes.DateTime)
        if issubclass(expected_type, String):
            return isinstance(actual_type, sqltypes.String)
        return isinstance(actual_type, expected_type)

    @staticmethod
    def _row_to_dict(row: Any) -> RowData | None:
        if row is None:
            return None
        return dict(row._mapping)

    @staticmethod
    def _filter_values(
        table: Table,
        values: Mapping[str, Any],
        allowed: Sequence[str],
    ) -> RowData:
        unknown = sorted(set(values) - set(allowed))
        if unknown:
            raise DatabaseConfigurationError(
                f"{table.name} 不支持的字段: {', '.join(unknown)}"
            )
        return dict(values)

    @staticmethod
    def _validate_satellite_record_limit(value: int | None) -> None:
        if value is not None and value <= 0:
            raise DatabaseConfigurationError("单星历史数据上限必须是正整数或 None")

    @staticmethod
    def _normalize_satellite_status(value: Any) -> str:
        status = str(value).strip()
        if status not in {"有效", "失效"}:
            raise DatabaseConfigurationError("卫星状态必须是 有效 或 失效")
        return status

    def _get_satellite_record_limit(self) -> int | None:
        metainfo = self.get_metainfo()
        if not metainfo:
            return None
        return metainfo["satellite_record_limit"]

    def _insert_row(self, table: Table, values: Mapping[str, Any]) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(insert(table).values(**values))
            return int(result.inserted_primary_key[0])

    def _get_by_id(self, table: Table, record_id: int) -> RowData | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(table).where(table.c.id == record_id)).first()
        return self._row_to_dict(row)

    def _list_rows(self, table: Table) -> list[RowData]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(table).order_by(table.c.id)).all()
        return [dict(row._mapping) for row in rows]

    def _update_by_id(
        self,
        table: Table,
        record_id: int,
        values: Mapping[str, Any],
    ) -> bool:
        if not values:
            return self._get_by_id(table, record_id) is not None
        with self.engine.begin() as conn:
            result = conn.execute(
                update(table).where(table.c.id == record_id).values(**values)
            )
        return result.rowcount > 0

    def _delete_by_id(self, table: Table, record_id: int) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(delete(table).where(table.c.id == record_id))
        return result.rowcount > 0

    def _migrate_fixed_schema(self) -> None:
        inspector = inspect(self.engine)
        if not inspector.has_table("satellite_groups"):
            return

        rocket_columns = {
            column["name"] for column in inspector.get_columns("rockets")
        }
        if "serial_number" not in rocket_columns:
            self._add_nullable_column(
                "rockets",
                Column("serial_number", String(64), nullable=True),
            )

        satellite_group_columns = {
            column["name"] for column in inspector.get_columns("satellite_groups")
        }
        if "valid_satellite_count" not in satellite_group_columns:
            self._add_nullable_column(
                "satellite_groups",
                Column("valid_satellite_count", Integer, nullable=True),
            )
        self._fill_null_column(
            "satellite_groups",
            "valid_satellite_count",
            0,
        )
        if "invalid_satellite_count" not in satellite_group_columns:
            self._add_nullable_column(
                "satellite_groups",
                Column("invalid_satellite_count", Integer, nullable=True),
            )
        self._fill_null_column(
            "satellite_groups",
            "invalid_satellite_count",
            0,
        )
        if "raw_tle" not in satellite_group_columns:
            self._add_nullable_column(
                "satellite_groups",
                Column("raw_tle", Text, nullable=True),
            )

    def _migrate_group_table_schema(self, group_id: int) -> None:
        table_name = self.get_group_table_name(group_id)
        inspector = inspect(self.engine)
        if not inspector.has_table(table_name):
            return

        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if "status" not in existing_columns:
            self._add_nullable_column(
                table_name,
                Column("status", String(16), nullable=True),
            )
        self._fill_null_column(table_name, "status", "有效")
        if "raw_tle" not in existing_columns:
            self._add_nullable_column(
                table_name,
                Column("raw_tle", Text, nullable=True),
            )

    def _migrate_satellite_table_schema(self, intl_designator: str) -> None:
        table_name = self.get_satellite_table_name(intl_designator)
        inspector = inspect(self.engine)
        if not inspector.has_table(table_name):
            return

        existing_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if "raw_tle" not in existing_columns:
            self._add_nullable_column(
                table_name,
                Column("raw_tle", Text, nullable=True),
            )

    def _add_nullable_column(self, table_name: str, column: Column) -> None:
        preparer = self.engine.dialect.identifier_preparer
        table_sql = preparer.quote(table_name)
        column_sql = preparer.quote(column.name)
        column_type_sql = column.type.compile(dialect=self.engine.dialect)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {table_sql} "
                    f"ADD COLUMN {column_sql} {column_type_sql}"
                )
            )

    def _fill_null_column(
        self,
        table_name: str,
        column_name: str,
        value: Any,
    ) -> None:
        preparer = self.engine.dialect.identifier_preparer
        table_sql = preparer.quote(table_name)
        column_sql = preparer.quote(column_name)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {table_sql} "
                    f"SET {column_sql} = :value "
                    f"WHERE {column_sql} IS NULL"
                ),
                {"value": value},
            )

    def _trim_satellite_records(self, table: Table) -> None:
        limit = self._get_satellite_record_limit()
        if limit is None:
            return

        with self.engine.begin() as conn:
            kept_first_ids = conn.execute(
                select(table.c.id).order_by(
                    table.c.epoch_at.desc(),
                    table.c.id.desc(),
                )
            ).scalars().all()
            delete_ids = kept_first_ids[limit:]
            if delete_ids:
                conn.execute(delete(table).where(table.c.id.in_(delete_ids)))

    def _enrich_orbit_rows(self, rows: Sequence[RowData]) -> list[RowData]:
        return [self._enrich_orbit_row(row) for row in rows]

    def _enrich_orbit_row(self, row: RowData | None) -> RowData | None:
        if row is None:
            return None
        enriched = dict(row)
        enriched.update(self._orbit_values_from_raw_tle(enriched.get("raw_tle")))
        return enriched

    @staticmethod
    def _orbit_values_from_raw_tle(raw_tle: Any) -> RowData:
        empty_values = {
            "inclination_deg": None,
            "perigee_km": None,
            "apogee_km": None,
            "eccentricity": None,
        }
        if raw_tle is None or str(raw_tle).strip() == "":
            return empty_values

        try:
            parsed_tle = parse_tle(str(raw_tle))
        except (TleParseError, ValueError):
            return empty_values

        return {
            "inclination_deg": parsed_tle["inclination_deg"],
            "perigee_km": parsed_tle["perigee_km"],
            "apogee_km": parsed_tle["apogee_km"],
            "eccentricity": parsed_tle["eccentricity"],
        }

    @staticmethod
    def _safe_table_name(prefix: str, raw_value: str) -> str:
        value = str(raw_value).strip()
        if value == "":
            raise DatabaseConfigurationError("动态表名来源不能为空")
        safe_value = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
        if safe_value == "":
            safe_value = "value"
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}_{safe_value[:40]}_{digest}"

    @staticmethod
    def _intl_designator_sort_key(intl_designator: str) -> tuple[str, int, str]:
        launch_key, piece = DatabaseManager._split_intl_designator(intl_designator)
        return (launch_key, DatabaseManager._piece_rank(piece), intl_designator)

    @staticmethod
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

    @staticmethod
    def _piece_rank(piece: str) -> int:
        rank = 0
        for char in piece:
            rank = rank * 26 + (ord(char) - ord("A") + 1)
        return rank

    def _group_table(self, group_id: int) -> Table:
        return Table(
            self.get_group_table_name(group_id),
            MetaData(),
            Column("id", Integer, primary_key=True),
            Column("epoch_at", DateTime(timezone=True), nullable=False),
            Column("intl_designator", String(64), nullable=False),
            Column("status", String(16), nullable=True),
            Column("raw_tle", Text, nullable=True),
        )

    def _satellite_table(self, intl_designator: str) -> Table:
        return Table(
            self.get_satellite_table_name(intl_designator),
            MetaData(),
            Column("id", Integer, primary_key=True),
            Column("epoch_at", DateTime(timezone=True), nullable=False),
            Column("raw_tle", Text, nullable=True),
        )

    @staticmethod
    def _to_utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
