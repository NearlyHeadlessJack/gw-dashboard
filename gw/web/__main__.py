"""命令行启动 Web 服务。"""

from __future__ import annotations

import logging
from typing import Sequence

import uvicorn

from gw.config import load_config
from gw.web.app import create_app


def configure_console_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def main(argv: Sequence[str] | None = None) -> None:
    configure_console_logging()
    config = load_config(argv)
    logging.getLogger(__name__).info(
        "gw-dashboard starting: host=%s port=%s reload=%s frontend_dist=%s",
        config.backend.host,
        config.backend.port,
        config.backend.reload,
        config.frontend.dist_dir,
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
