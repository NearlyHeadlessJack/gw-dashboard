"""启动前检查流程。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gw.config import AppConfig
from gw.database import DatabaseManager
from gw.scraper.celestrak import CELESTRAK_URL, fetch_tle
from gw.scraper.huiji import HUIJI_URL, fetch_page


HUIJI_CHECK_NAME = "huiji_wiki"
TLE_CHECK_NAME = "tle_url"
TLE_CHECK_INTL_DESIGNATOR = "1998-067A"


@dataclass(frozen=True)
class StartupCheck:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class StartupCheckResult:
    config: AppConfig
    database: DatabaseManager
    checks: list[StartupCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


class StartupCheckError(RuntimeError):
    """启动前检查失败。"""

    def __init__(self, checks: list[StartupCheck]):
        self.checks = checks
        failed = [check for check in checks if not check.ok]
        message = "; ".join(f"{check.name}: {check.message}" for check in failed)
        super().__init__(f"启动前检查失败: {message}")


DatabaseManagerFactory = Callable[[str, object], DatabaseManager]
HuijiFetcher = Callable[..., str]
TleFetcher = Callable[..., str]


def run_startup_checks(
    config: AppConfig,
    *,
    database_manager_factory: DatabaseManagerFactory = DatabaseManager,
    huiji_fetcher: HuijiFetcher = fetch_page,
    tle_fetcher: TleFetcher = fetch_tle,
    raise_on_failure: bool = True,
) -> StartupCheckResult:
    """执行加载配置后的启动前检查。"""
    database = database_manager_factory(
        config.database.type,
        config.database.connection,
    )
    checks = [
        _check_database_connection(database),
        _check_database_schema(database),
        _check_huiji_connection(config, huiji_fetcher),
        _check_tle_connection(config, tle_fetcher),
    ]
    result = StartupCheckResult(config=config, database=database, checks=checks)
    if raise_on_failure and not result.ok:
        raise StartupCheckError(checks)
    return result


def _check_database_connection(database: DatabaseManager) -> StartupCheck:
    try:
        if database.test_connection():
            return StartupCheck("database_connection", True, "数据库连接成功")
        return StartupCheck("database_connection", False, "数据库连接失败")
    except Exception as exc:
        return StartupCheck("database_connection", False, str(exc))


def _check_database_schema(database: DatabaseManager) -> StartupCheck:
    try:
        database.initialize_database()
        return StartupCheck("database_schema", True, "数据库表结构检查通过")
    except Exception as exc:
        return StartupCheck("database_schema", False, str(exc))


def _check_huiji_connection(
    config: AppConfig,
    huiji_fetcher: HuijiFetcher,
) -> StartupCheck:
    url = config.scraper.huiji_url or HUIJI_URL
    try:
        html = huiji_fetcher(url=url, timeout=config.scraper.network_timeout_seconds)
        if html.strip():
            return StartupCheck(HUIJI_CHECK_NAME, True, "灰机 wiki 连接成功")
        return StartupCheck(HUIJI_CHECK_NAME, False, "灰机 wiki 返回空内容")
    except Exception as exc:
        return StartupCheck(HUIJI_CHECK_NAME, False, str(exc))


def _check_tle_connection(
    config: AppConfig,
    tle_fetcher: TleFetcher,
) -> StartupCheck:
    url = config.scraper.celestrak_url or CELESTRAK_URL
    try:
        tle_text = tle_fetcher(
            TLE_CHECK_INTL_DESIGNATOR,
            url=url,
            timeout=config.scraper.network_timeout_seconds,
        )
        if "1 " in tle_text and "2 " in tle_text:
            return StartupCheck(TLE_CHECK_NAME, True, "TLE 获取 URL 连接成功")
        return StartupCheck(TLE_CHECK_NAME, False, "TLE 获取 URL 返回内容不是 TLE")
    except Exception as exc:
        return StartupCheck(TLE_CHECK_NAME, False, str(exc))
