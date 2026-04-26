import pytest
from sqlalchemy.exc import OperationalError

from gw.database import DatabaseConfigurationError, DatabaseManager
from gw.database import manager as manager_module


def render_url(url):
    if hasattr(url, "render_as_string"):
        return url.render_as_string(hide_password=False)
    return str(url)


class FakeConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        self.statements.append(str(statement))


class FakeEngine:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.connection = FakeConnection()

    def connect(self):
        if self.should_fail:
            raise OperationalError("SELECT 1", {}, RuntimeError("server down"))
        return self.connection


def test_sqlite_memory_connection_uses_real_engine():
    db = DatabaseManager("sqlite3", ":memory:")

    assert render_url(db.database_url) == "sqlite+pysqlite:///:memory:"
    assert db.test_connection() is True


def test_sqlite_file_connection_uses_database_path(tmp_path):
    db_path = tmp_path / "gw.sqlite3"

    db = DatabaseManager("sqlite3", db_path)

    assert render_url(db.database_url).endswith(str(db_path))
    assert db.test_connection() is True
    assert db_path.exists()


def test_sqlite_file_connection_creates_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "database" / "gw.sqlite3"

    db = DatabaseManager("sqlite3", db_path)

    assert db.test_connection() is True
    assert db_path.exists()


def test_mysql_mapping_builds_engine_and_tests_connection(monkeypatch):
    created = {}
    fake_engine = FakeEngine()

    def fake_create_engine(url, **kwargs):
        created["url"] = url
        created["kwargs"] = kwargs
        return fake_engine

    monkeypatch.setattr(manager_module, "create_engine", fake_create_engine)

    db = DatabaseManager(
        "mysql",
        {
            "user": "gw",
            "password": "secret",
            "host": "mysql.local",
            "port": 3307,
            "database": "satellites",
        },
    )

    assert db.db_type == "mysql"
    assert render_url(created["url"]) == (
        "mysql+pymysql://gw:secret@mysql.local:3307/satellites"
    )
    assert created["kwargs"] == {"pool_pre_ping": True}
    assert db.test_connection() is True
    assert fake_engine.connection.statements == ["SELECT 1"]


def test_pgsql_mapping_builds_engine_with_postgres_alias(monkeypatch):
    created = {}

    def fake_create_engine(url, **kwargs):
        created["url"] = url
        created["kwargs"] = kwargs
        return FakeEngine()

    monkeypatch.setattr(manager_module, "create_engine", fake_create_engine)

    db = DatabaseManager(
        "postgres",
        {
            "username": "gw",
            "password": "secret",
            "host": "pgsql.local",
            "database": "satellites",
        },
    )

    assert db.db_type == "pgsql"
    assert render_url(created["url"]) == (
        "postgresql+psycopg://gw:secret@pgsql.local:5432/satellites"
    )
    assert created["kwargs"] == {"pool_pre_ping": True}


def test_server_connection_accepts_full_sqlalchemy_url(monkeypatch):
    created = {}

    def fake_create_engine(url, **kwargs):
        created["url"] = url
        created["kwargs"] = kwargs
        return FakeEngine()

    monkeypatch.setattr(manager_module, "create_engine", fake_create_engine)

    db = DatabaseManager("pgsql", "postgresql+psycopg://gw:secret@localhost/gw")

    assert db.db_type == "pgsql"
    assert created["url"] == "postgresql+psycopg://gw:secret@localhost/gw"
    assert db.test_connection() is True


def test_test_connection_returns_false_when_engine_cannot_connect(monkeypatch):
    monkeypatch.setattr(
        manager_module,
        "create_engine",
        lambda url, **kwargs: FakeEngine(should_fail=True),
    )

    db = DatabaseManager(
        "mysql",
        {
            "user": "gw",
            "password": "secret",
            "host": "mysql.local",
            "database": "satellites",
        },
    )

    assert db.test_connection() is False


def test_unknown_database_type_raises_configuration_error():
    with pytest.raises(DatabaseConfigurationError, match="不支持的数据库类型"):
        DatabaseManager("oracle", "unused")


def test_server_connection_requires_mapping_or_url():
    with pytest.raises(DatabaseConfigurationError, match="SQLAlchemy URL 字符串或 dict"):
        DatabaseManager("mysql", "mysql.local:3306")


def test_server_mapping_requires_user_and_database():
    with pytest.raises(DatabaseConfigurationError, match="缺少数据库连接字段"):
        DatabaseManager("pgsql", {"host": "localhost"})
