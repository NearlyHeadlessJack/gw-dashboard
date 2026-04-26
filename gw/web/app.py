"""FastAPI 应用入口。"""

from __future__ import annotations

import time
import logging
from contextlib import asynccontextmanager
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from gw.config import AppConfig, load_config
from gw.daemon import DashboardDaemon
from gw.database import DatabaseConfigurationError, DatabaseManager, DatabaseQueryError
from gw.utils.update_database import update_satellite_database
from gw.web.api import (
    build_dashboard,
    build_map_points,
    build_map_satellites,
    get_group_detail,
    get_satellite_detail,
    get_satellite_history,
    list_groups,
    list_launches,
    list_satellites,
)


logger = logging.getLogger(__name__)


class TtlCache:
    """进程内短期缓存，用于降低仪表盘聚合查询压力。"""

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, Any]] = {}

    def get_or_set(self, key: str, ttl_seconds: int, factory: Callable[[], Any]) -> Any:
        if ttl_seconds <= 0:
            return factory()

        now = time.monotonic()
        cached = self._values.get(key)
        if cached and cached[0] > now:
            return cached[1]

        value = factory()
        self._values[key] = (now + ttl_seconds, value)
        return value

    def clear(self) -> None:
        self._values.clear()


def create_app(
    config: AppConfig | None = None,
    *,
    database: DatabaseManager | None = None,
    start_daemon: bool = True,
) -> FastAPI:
    """创建 Web API 应用。"""
    app_config = config or load_config()
    db = database or DatabaseManager(
        app_config.database.type,
        app_config.database.connection,
    )
    logger.info("database initializing: type=%s", app_config.database.type)
    db.initialize_database()
    _ensure_metainfo_defaults(db, app_config)
    cache = TtlCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        daemon: DashboardDaemon | None = None
        if start_daemon:
            daemon = _create_data_daemon(app_config, db)
            app.state.daemon = daemon
            logger.info(
                "daemon launching in background: interval=%ss valid_duration=%ss "
                "satellite_record_limit=%s",
                app_config.daemon.update_check_interval_seconds,
                app_config.daemon.data_valid_duration_seconds,
                app_config.daemon.satellite_record_limit,
            )
            daemon.start()
        else:
            app.state.daemon = None
            logger.info("daemon disabled for this app instance")

        try:
            yield
        finally:
            if daemon is not None:
                logger.info("daemon shutdown requested by web app")
                daemon.stop()
                daemon.join(timeout=10)
                if daemon.is_alive():
                    logger.warning("daemon did not stop within timeout")

    app = FastAPI(title="GW Dashboard API", version="0.1.0", lifespan=lifespan)
    app.state.config = app_config
    app.state.database = db
    app.state.cache = cache

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_config.backend.cors_origins,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "database": db.test_connection(),
            "cache_ttl_seconds": app_config.backend.cache_ttl_seconds,
        }

    @app.get("/api/dashboard")
    def dashboard() -> Any:
        return _cached(
            app,
            "dashboard",
            lambda: build_dashboard(db),
        )

    @app.get("/api/groups")
    def groups() -> Any:
        return _cached(app, "groups", lambda: list_groups(db))

    @app.get("/api/launches")
    def launches() -> Any:
        return _cached(app, "launches", lambda: list_launches(db))

    @app.get("/api/satellites")
    def satellites() -> Any:
        return _cached(app, "satellites", lambda: list_satellites(db))

    @app.get("/api/groups/{intl_designator}")
    def group_detail(intl_designator: str) -> Any:
        detail = _handle_database_errors(
            lambda: get_group_detail(db, intl_designator)
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="卫星组不存在")
        return detail

    @app.get("/api/satellites/{intl_designator}")
    def satellite_detail(intl_designator: str) -> Any:
        detail = _handle_database_errors(
            lambda: get_satellite_detail(db, intl_designator)
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="卫星不存在")
        return detail

    @app.get("/api/satellites/{intl_designator}/history")
    def satellite_history(intl_designator: str) -> Any:
        return _handle_database_errors(lambda: get_satellite_history(db, intl_designator))

    @app.get("/api/map/groups")
    def map_groups(
        at: str | None = Query(default=None, description="ISO-8601 UTC time"),
    ) -> Any:
        moment = _parse_time_query(at)
        cache_key = f"map:groups:{moment.isoformat(timespec='seconds')}"
        return _cached(
            app,
            cache_key,
            lambda: build_map_satellites(db, at=moment),
            ttl_override=min(app_config.backend.cache_ttl_seconds, 10),
        )

    @app.get("/api/map/points")
    def map_points(
        at: str | None = Query(default=None, description="ISO-8601 UTC time"),
    ) -> Any:
        moment = _parse_time_query(at)
        cache_key = f"map:points:{moment.isoformat(timespec='seconds')}"
        return _cached(
            app,
            cache_key,
            lambda: build_map_points(db, at=moment),
            ttl_override=min(app_config.backend.cache_ttl_seconds, 10),
        )

    @app.get("/api/map/satellites")
    def map_satellites(
        at: str | None = Query(default=None, description="ISO-8601 UTC time"),
    ) -> Any:
        return map_groups(at)

    _mount_frontend(app, app_config)
    return app


def _ensure_metainfo_defaults(database: DatabaseManager, config: AppConfig) -> None:
    metainfo = database.get_metainfo()
    if metainfo is not None:
        logger.info(
            "database metainfo loaded: last_updated_at=%s valid_duration=%ss "
            "satellite_record_limit=%s",
            metainfo["last_updated_at"],
            metainfo["valid_duration_seconds"],
            metainfo["satellite_record_limit"],
        )
        return

    database.set_metainfo(
        None,
        valid_duration_seconds=config.daemon.data_valid_duration_seconds,
        satellite_record_limit=config.daemon.satellite_record_limit,
    )
    logger.info(
        "database metainfo initialized: valid_duration=%ss satellite_record_limit=%s",
        config.daemon.data_valid_duration_seconds,
        config.daemon.satellite_record_limit,
    )


def _create_data_daemon(
    config: AppConfig,
    database: DatabaseManager,
) -> DashboardDaemon:
    return DashboardDaemon(
        config,
        database,
        web_server_starter=lambda: logger.info("web server is managed by uvicorn"),
        frontend_server_starter=lambda: logger.info(
            "frontend is served by backend from dist_dir=%s",
            config.frontend.dist_dir,
        ),
        data_updater=lambda: update_satellite_database(
            database,
            now=datetime.now(timezone.utc),
        ),
    )


def _cached(
    app: FastAPI,
    key: str,
    factory: Callable[[], Any],
    *,
    ttl_override: int | None = None,
) -> Any:
    ttl = ttl_override
    if ttl is None:
        ttl = app.state.config.backend.cache_ttl_seconds
    return _handle_database_errors(
        lambda: app.state.cache.get_or_set(key, ttl, factory)
    )


def _handle_database_errors(factory: Callable[[], Any]) -> Any:
    try:
        return factory()
    except DatabaseConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabaseQueryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _parse_time_query(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="时间格式必须是 ISO-8601") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _mount_frontend(app: FastAPI, config: AppConfig) -> None:
    dist_dir = _resolve_frontend_dist_dir(config.frontend.dist_dir)
    index_file = dist_dir / "index.html"
    if not index_file.exists():
        logger.warning("frontend dist not found: %s", dist_dir)
        return
    logger.info("frontend mounted: dist_dir=%s", dist_dir)

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_spa(path: str) -> FileResponse:
        if path == "" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        requested_file = (dist_dir / path).resolve()
        if requested_file.is_file() and requested_file.is_relative_to(dist_dir):
            return FileResponse(requested_file)
        return FileResponse(index_file)


def _resolve_frontend_dist_dir(raw_dist_dir: str) -> Path:
    dist_dir = Path(raw_dist_dir)
    if dist_dir.is_absolute():
        return dist_dir
    project_root = Path(__file__).resolve().parents[2]
    return project_root / dist_dir
