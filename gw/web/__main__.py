"""命令行启动 Web 服务。"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Sequence

import uvicorn

from gw.config import AppConfig, load_config, parse_startup_args
from gw.web.app import create_app
from gw.web.runtime import database_connection_for_log, log_frontend_entry


STARTUP_FAILURE = 3
FRONTEND_BUILD_FAILURE = 4


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


def build_frontend_static(
    logger: logging.Logger,
    *,
    frontend_dir: Path | None = None,
) -> None:
    source_dir = frontend_dir or Path(__file__).resolve().parents[2] / "frontend"
    package_json = source_dir / "package.json"
    if not package_json.exists():
        logger.error(
            "frontend source not found: %s; -d requires running from a source checkout",
            source_dir,
        )
        raise SystemExit(FRONTEND_BUILD_FAILURE)

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        logger.error("npm not found; -d requires Node.js/npm to build frontend assets")
        raise SystemExit(FRONTEND_BUILD_FAILURE)

    logger.info(
        "building frontend static assets: cwd=%s command=%s run build",
        source_dir,
        npm,
    )
    try:
        subprocess.run([npm, "run", "build"], cwd=source_dir, check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("frontend build failed: exit_code=%s", exc.returncode)
        raise SystemExit(FRONTEND_BUILD_FAILURE) from exc


def main(argv: Sequence[str] | None = None) -> None:
    configure_console_logging()
    args = parse_startup_args(argv)
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
    if args.build_frontend:
        build_frontend_static(logger)
    run_web_server(config, logger)


if __name__ == "__main__":
    main()
