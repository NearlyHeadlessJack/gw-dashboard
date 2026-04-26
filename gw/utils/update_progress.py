"""数据库更新过程的终端进度输出。"""

from __future__ import annotations

import sys
from typing import Protocol, TextIO


class UpdateProgressReporter(Protocol):
    """数据库更新过程进度回调。"""

    def launch_fetch_started(self) -> None:
        """开始获取发射信息。"""

    def launch_fetch_finished(self, group_count: int) -> None:
        """发射信息获取完成。"""

    def tle_fetch_started(self, total_groups: int) -> None:
        """开始获取 TLE。"""

    def tle_group_started(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        """开始获取某组 TLE。"""

    def tle_group_finished(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
        tle_count: int,
    ) -> None:
        """某组 TLE 获取完成。"""

    def tle_group_failed(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        """某组 TLE 获取失败。"""

    def tle_fetch_finished(self, total_groups: int) -> None:
        """TLE 获取完成。"""


class NullUpdateProgressReporter:
    """默认空进度回调。"""

    def launch_fetch_started(self) -> None:
        pass

    def launch_fetch_finished(self, group_count: int) -> None:
        pass

    def tle_fetch_started(self, total_groups: int) -> None:
        pass

    def tle_group_started(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        pass

    def tle_group_finished(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
        tle_count: int,
    ) -> None:
        pass

    def tle_group_failed(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        pass

    def tle_fetch_finished(self, total_groups: int) -> None:
        pass


class ConsoleUpdateProgressReporter:
    """输出适合终端查看的数据更新进度。"""

    def __init__(self, stream: TextIO | None = None, *, bar_width: int = 24) -> None:
        self.stream = stream or sys.stderr
        self.bar_width = bar_width

    def first_run_waiting(self) -> None:
        self._write_line("首次运行，请等待爬取数据完成")

    def launch_fetch_started(self) -> None:
        self._write_line("正在获取卫星发射信息")

    def launch_fetch_finished(self, group_count: int) -> None:
        self._write_line(f"卫星发射信息获取成功，共 {group_count} 组")

    def tle_fetch_started(self, total_groups: int) -> None:
        if total_groups <= 0:
            self._write_line("没有需要获取 TLE 的卫星组")
            return
        self._write_line(f"正在获取 TLE 数据，共 {total_groups} 组")

    def tle_group_started(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        if total_groups <= 0:
            return
        self._write_progress(index - 1, total_groups, f"{intl_designator} 获取中")

    def tle_group_finished(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
        tle_count: int,
    ) -> None:
        if total_groups <= 0:
            return
        self._write_progress(index, total_groups, f"{intl_designator} {tle_count} 条")

    def tle_group_failed(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        if total_groups <= 0:
            return
        self._write_progress(index - 1, total_groups, f"{intl_designator} 获取失败")

    def tle_fetch_finished(self, total_groups: int) -> None:
        if total_groups > 0:
            self._write_line("TLE 数据获取完成")

    def _write_progress(self, current: int, total: int, detail: str) -> None:
        current = max(0, min(current, total))
        filled = round(self.bar_width * current / total)
        bar = "#" * filled + "-" * (self.bar_width - filled)
        percent = round(100 * current / total)
        self._write_line(f"TLE [{bar}] {current}/{total} {percent:3d}% {detail}")

    def _write_line(self, message: str) -> None:
        print(message, file=self.stream, flush=True)
