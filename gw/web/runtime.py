"""Web 服务运行时日志辅助函数。"""

from __future__ import annotations

import logging
import webbrowser
from collections.abc import Callable

from gw.config import AppConfig


def frontend_entry_url(config: AppConfig) -> str:
    """返回用户浏览器应打开的前端入口 URL。"""
    host = config.backend.host.strip() or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{config.backend.port}"


def terminal_hyperlink(url: str, label: str | None = None) -> str:
    """生成支持 OSC 8 的终端超链接文本。"""
    text = label or url
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def database_connection_for_log(connection: object) -> object:
    """返回适合日志输出的数据库连接信息，避免泄露密码。"""
    if isinstance(connection, dict):
        return {
            key: ("***" if "password" in str(key).lower() else value)
            for key, value in connection.items()
        }
    connection_text = str(connection)
    if "://" in connection_text and "@" in connection_text:
        return "<configured sqlalchemy url>"
    return connection_text


def log_frontend_entry(logger: logging.Logger, config: AppConfig) -> None:
    """在 Web 服务启动后打印前端入口。"""
    frontend_url = frontend_entry_url(config)
    logger.info(
        "web service started: frontend entry URL: %s (%s)",
        frontend_url,
        terminal_hyperlink(frontend_url, "open dashboard"),
    )


def open_frontend_entry_in_browser(
    logger: logging.Logger,
    config: AppConfig,
    *,
    opener: Callable[[str], bool] | None = None,
) -> None:
    """尝试用系统默认浏览器打开前端入口。"""
    frontend_url = frontend_entry_url(config)
    open_url = opener or (lambda url: webbrowser.open(url, new=2))
    try:
        opened = open_url(frontend_url)
    except Exception as exc:
        logger.warning("could not open dashboard in browser: %s", exc)
        return

    if opened:
        logger.info("dashboard opened in browser: %s", frontend_url)
    else:
        logger.warning("could not open dashboard in browser: %s", frontend_url)
