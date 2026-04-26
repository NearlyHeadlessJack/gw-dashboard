"""命令行启动 Web 服务。"""

from __future__ import annotations

import logging
from typing import Sequence

import uvicorn

from gw.config import AppConfig, load_config
from gw.web.app import create_app


def configure_console_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


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


def main(argv: Sequence[str] | None = None) -> None:
    configure_console_logging()
    config = load_config(argv)
    logger = logging.getLogger(__name__)
    frontend_url = frontend_entry_url(config)
    logger.info(
        "gw-dashboard starting: host=%s port=%s reload=%s frontend_dist=%s",
        config.backend.host,
        config.backend.port,
        config.backend.reload,
        config.frontend.dist_dir,
    )
    logger.info(
        "database configured: type=%s connection=%s",
        config.database.type,
        database_connection_for_log(config.database.connection),
    )
    logger.info(
        "frontend entry URL: %s (%s)",
        frontend_url,
        terminal_hyperlink(frontend_url, "open dashboard"),
    )
    uvicorn.run(
        create_app(config),
        host=config.backend.host,
        port=config.backend.port,
        reload=config.backend.reload,
        log_config=None,
    )


if __name__ == "__main__":
    main()
