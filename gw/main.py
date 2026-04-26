"""后端启动入口的配置加载部分。"""

from __future__ import annotations

from typing import Mapping, Sequence

from gw.config import AppConfig, load_config
from gw.startup import StartupCheckResult, run_startup_checks


def load_startup_config(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    """加载启动配置；真正启动 web/daemon 的逻辑后续再接入。"""
    return load_config(argv, env=env)


def main(argv: Sequence[str] | None = None) -> StartupCheckResult:
    """加载配置并执行启动前检查。"""
    config = load_startup_config(argv)
    return run_startup_checks(config)


if __name__ == "__main__":
    main()
