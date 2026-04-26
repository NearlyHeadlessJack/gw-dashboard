"""包级命令行入口。"""

from __future__ import annotations

from typing import Sequence

from gw.web.__main__ import main as web_main


def main(argv: Sequence[str] | None = None) -> None:
    """启动 gw-dashboard Web 服务。"""
    web_main(argv)


if __name__ == "__main__":
    main()
