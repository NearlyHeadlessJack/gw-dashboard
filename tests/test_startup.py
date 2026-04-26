import pytest

from gw.config import AppConfig, DatabaseConfig, ScraperConfig
from gw import main as main_module
from gw.startup import StartupCheckError, run_startup_checks


class FakeDatabase:
    def __init__(self, connection_ok=True, schema_error=None):
        self.connection_ok = connection_ok
        self.schema_error = schema_error
        self.test_connection_called = False
        self.initialize_database_called = False

    def test_connection(self):
        self.test_connection_called = True
        return self.connection_ok

    def initialize_database(self):
        self.initialize_database_called = True
        if self.schema_error is not None:
            raise self.schema_error


def make_config():
    return AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        scraper=ScraperConfig(
            huiji_url="https://huiji.example/wiki",
            celestrak_url="https://tle.example/gp.php",
            network_timeout_seconds=7,
        ),
    )


def test_run_startup_checks_success():
    config = make_config()
    database = FakeDatabase()
    calls = []

    def fake_huiji_fetcher(**kwargs):
        calls.append(("huiji", kwargs))
        return "<html>星网</html>"

    def fake_tle_fetcher(intl_designator, **kwargs):
        calls.append(("tle", intl_designator, kwargs))
        return "ISS\n1 25544U 98067A\n2 25544"

    result = run_startup_checks(
        config,
        database_manager_factory=lambda db_type, connection: database,
        huiji_fetcher=fake_huiji_fetcher,
        tle_fetcher=fake_tle_fetcher,
    )

    assert result.ok is True
    assert result.database is database
    assert database.test_connection_called
    assert database.initialize_database_called
    assert [check.name for check in result.checks] == [
        "database_connection",
        "database_schema",
        "huiji_wiki",
        "tle_url",
    ]
    assert calls == [
        ("huiji", {"url": "https://huiji.example/wiki", "timeout": 7}),
        (
            "tle",
            "1998-067A",
            {"url": "https://tle.example/gp.php", "timeout": 7},
        ),
    ]


def test_run_startup_checks_collects_failures_without_raising():
    config = make_config()
    database = FakeDatabase(connection_ok=False, schema_error=RuntimeError("bad schema"))

    result = run_startup_checks(
        config,
        database_manager_factory=lambda db_type, connection: database,
        huiji_fetcher=lambda **kwargs: "",
        tle_fetcher=lambda *args, **kwargs: "not tle",
        raise_on_failure=False,
    )

    assert result.ok is False
    assert [check.ok for check in result.checks] == [False, False, False, False]
    assert [check.message for check in result.checks] == [
        "数据库连接失败",
        "bad schema",
        "灰机 wiki 返回空内容",
        "TLE 获取 URL 返回内容不是 TLE",
    ]


def test_run_startup_checks_raises_with_failed_check_messages():
    config = make_config()
    database = FakeDatabase(connection_ok=False)

    with pytest.raises(StartupCheckError, match="database_connection"):
        run_startup_checks(
            config,
            database_manager_factory=lambda db_type, connection: database,
            huiji_fetcher=lambda **kwargs: "<html>ok</html>",
            tle_fetcher=lambda *args, **kwargs: "1 line\n2 line",
        )


def test_run_startup_checks_uses_default_scraper_urls():
    config = AppConfig(database=DatabaseConfig(type="sqlite3", connection=":memory:"))
    database = FakeDatabase()
    calls = []

    def fake_huiji_fetcher(**kwargs):
        calls.append(("huiji", kwargs["url"], kwargs["timeout"]))
        return "<html>ok</html>"

    def fake_tle_fetcher(intl_designator, **kwargs):
        calls.append(("tle", kwargs["url"], kwargs["timeout"]))
        return "1 line\n2 line"

    run_startup_checks(
        config,
        database_manager_factory=lambda db_type, connection: database,
        huiji_fetcher=fake_huiji_fetcher,
        tle_fetcher=fake_tle_fetcher,
    )

    assert calls == [
        ("huiji", "https://sat.huijiwiki.com/wiki/%E6%98%9F%E7%BD%91", 30),
        ("tle", "https://celestrak.org/NORAD/elements/gp.php", 30),
    ]


def test_main_loads_config_then_runs_startup_checks(monkeypatch):
    config = make_config()
    expected = object()

    monkeypatch.setattr(main_module, "load_startup_config", lambda argv: config)
    monkeypatch.setattr(
        main_module,
        "run_startup_checks",
        lambda loaded_config: expected,
    )

    assert main_module.main(["-c", "config.yaml"]) is expected
