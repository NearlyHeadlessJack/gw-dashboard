"""命令行启动 Web 服务。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Sequence

import uvicorn

from gw.config import AppConfig, load_config
from gw.web.app import create_app
from gw.web.runtime import database_connection_for_log, log_frontend_entry


STARTUP_FAILURE = 3


def configure_console_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


class FrontendEntryServer(uvicorn.Server):
    """Uvicorn server that prints the frontend URL after sockets are listening."""

    def __init__(
        self,
        config: uvicorn.Config,
        *,
        on_started: Callable[[], None],
    ) -> None:
        super().__init__(config=config)
        self._on_started = on_started
        self._notified_started = False

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets=sockets)
        if self.started and not self._notified_started:
            self._notified_started = True
            self._on_started()


def run_web_server(config: AppConfig, logger: logging.Logger) -> None:
    server_config = uvicorn.Config(
        create_app(config, log_frontend_on_startup=False),
        host=config.backend.host,
        port=config.backend.port,
        reload=config.backend.reload,
        log_config=None,
    )

    if server_config.reload and not isinstance(server_config.app, str):
        logging.getLogger("uvicorn.error").warning(
            "You must pass the application as an import string to enable 'reload'."
        )
        raise SystemExit(1)

    server = FrontendEntryServer(
        server_config,
        on_started=lambda: log_frontend_entry(logger, config),
    )
    try:
        server.run()
    except KeyboardInterrupt:
        pass

    if not server.started:
        raise SystemExit(STARTUP_FAILURE)


def main(argv: Sequence[str] | None = None) -> None:
    configure_console_logging()
    config = load_config(argv)
    logger = logging.getLogger(__name__)
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
    run_web_server(config, logger)


if __name__ == "__main__":
    main()
