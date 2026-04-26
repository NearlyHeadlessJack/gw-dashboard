"""命令行启动 Web 服务。"""

from __future__ import annotations

from typing import Sequence

import uvicorn

from gw.config import load_config
from gw.web.app import create_app


def main(argv: Sequence[str] | None = None) -> None:
    config = load_config(argv)
    uvicorn.run(
        create_app(config),
        host=config.backend.host,
        port=config.backend.port,
        reload=config.backend.reload,
    )


if __name__ == "__main__":
    main()
