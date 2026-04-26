"""守护进程线程逻辑。"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from gw.config import AppConfig


logger = logging.getLogger(__name__)


class ExpirationDatabase(Protocol):
    """daemon 当前需要的数据库接口。"""

    def is_update_expired(self) -> bool:
        """返回数据库数据是否过期。"""


@dataclass(frozen=True)
class DaemonCycleResult:
    """单次 daemon 检查循环的结果。"""

    expired_before_update: bool
    update_ran: bool
    expired_after_update: bool


class DashboardDaemon(threading.Thread):
    """星网数据后台守护线程。"""

    def __init__(
        self,
        config: AppConfig,
        database: ExpirationDatabase,
        *,
        web_server_starter: Callable[[], None] | None = None,
        frontend_server_starter: Callable[[], None] | None = None,
        data_updater: Callable[[], None] | None = None,
        daemon: bool = True,
        name: str = "gw-dashboard-daemon",
    ):
        super().__init__(name=name, daemon=daemon)
        self.config = config
        self.database = database
        self.web_server_starter = web_server_starter or self._start_web_server
        self.frontend_server_starter = (
            frontend_server_starter or self._start_frontend_server
        )
        self.data_updater = data_updater or self._update_data
        self._stop_event = threading.Event()
        self._services_started = False
        self.last_cycle_result: DaemonCycleResult | None = None
        self.last_error: BaseException | None = None

    @property
    def check_interval_seconds(self) -> int:
        """读取 daemon 更新检查间隔。"""
        return self.config.daemon.update_check_interval_seconds

    def stop(self) -> None:
        """请求 daemon 停止；如果正在睡眠会立即唤醒。"""
        logger.info("daemon stop requested")
        self._stop_event.set()

    def run(self) -> None:
        """线程入口：启动占位服务，然后循环检查数据库是否过期。"""
        logger.info(
            "daemon starting: check_interval=%ss",
            self.check_interval_seconds,
        )
        try:
            self.start_runtime_services()
        except Exception as exc:
            self.last_error = exc
            logger.exception("daemon runtime service startup failed")
            return

        while not self._stop_event.is_set():
            try:
                self.last_cycle_result = self.run_cycle()
            except Exception as exc:
                self.last_error = exc
                logger.exception("daemon cycle failed")
            self._stop_event.wait(self.check_interval_seconds)
        logger.info("daemon stopped")

    def start_runtime_services(self) -> None:
        """首次运行 daemon 时启动后端 web 服务和前端服务。"""
        if self._services_started:
            logger.info("daemon runtime services already started")
            return
        logger.info("daemon runtime services starting")
        self.web_server_starter()
        self.frontend_server_starter()
        self._services_started = True
        logger.info("daemon runtime services ready")

    def run_cycle(self) -> DaemonCycleResult:
        """执行一次数据库过期检查和必要的数据更新。"""
        logger.info("daemon cycle checking data expiration")
        expired_before_update = self.database.is_update_expired()
        if not expired_before_update:
            logger.info(
                "daemon cycle complete: data is fresh; next_check_in=%ss",
                self.check_interval_seconds,
            )
            return DaemonCycleResult(
                expired_before_update=False,
                update_ran=False,
                expired_after_update=False,
            )

        logger.info("daemon cycle detected expired data; update starting")
        self.data_updater()
        expired_after_update = self.database.is_update_expired()
        if expired_after_update:
            logger.warning("daemon cycle complete: data update ran but data is still expired")
        else:
            logger.info("daemon cycle complete: data update finished successfully")
        return DaemonCycleResult(
            expired_before_update=True,
            update_ran=True,
            expired_after_update=expired_after_update,
        )

    def _start_web_server(self) -> None:
        """后端 web 服务启动占位符。"""

    def _start_frontend_server(self) -> None:
        """前端服务启动占位符。"""

    def _update_data(self) -> None:
        """数据更新占位符。"""
