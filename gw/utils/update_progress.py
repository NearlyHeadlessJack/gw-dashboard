"""数据库更新过程的终端进度输出。"""

from __future__ import annotations

import sys
from typing import Protocol, TextIO

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeElapsedColumn


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

    def tle_fetch_failed(self, total_groups: int) -> None:
        """TLE 获取失败。"""


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

    def tle_fetch_failed(self, total_groups: int) -> None:
        pass


class ConsoleUpdateProgressReporter:
    """输出适合终端查看的数据更新进度。"""

    def __init__(self, stream: TextIO | None = None, *, bar_width: int = 24) -> None:
        self.stream = stream or sys.stderr
        self.bar_width = bar_width
        self.console = Console(file=self.stream)
        self._progress: Progress | None = None
        self._tle_task_id: TaskID | None = None

    def first_run_waiting(self) -> None:
        self._write_line("首次运行，请等待爬取数据完成")

    def launch_fetch_started(self) -> None:
        self._write_line("正在获取卫星发射信息")

    def launch_fetch_finished(self, group_count: int) -> None:
        self._write_line("卫星发射信息获取完成")

    def tle_fetch_started(self, total_groups: int) -> None:
        if total_groups <= 0:
            self._write_line("没有需要获取 TLE 的卫星组")
            return
        self._progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(bar_width=self.bar_width),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
        )
        self._progress.start()
        self._tle_task_id = self._progress.add_task(
            "正在获取 TLE 数据",
            total=total_groups,
        )

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
        if self._progress is not None and self._tle_task_id is not None:
            self._progress.update(self._tle_task_id, completed=index)

    def tle_group_failed(
        self,
        index: int,
        total_groups: int,
        intl_designator: str,
    ) -> None:
        pass

    def tle_fetch_finished(self, total_groups: int) -> None:
        if total_groups > 0:
            self._stop_progress()
            self._write_line("TLE 数据获取完成")

    def tle_fetch_failed(self, total_groups: int) -> None:
        if total_groups > 0:
            self._stop_progress()
            self._write_line("TLE 数据获取失败")

    def _stop_progress(self) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
            self._tle_task_id = None

    def _write_line(self, message: str) -> None:
        self.console.print(message)
