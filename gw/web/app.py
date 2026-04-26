"""FastAPI 应用入口。"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from gw.config import AppConfig, load_config
from gw.database import DatabaseConfigurationError, DatabaseManager, DatabaseQueryError
from gw.web.api import (
    build_dashboard,
    build_map_satellites,
    get_group_detail,
    get_satellite_detail,
    get_satellite_history,
    list_groups,
)


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
) -> FastAPI:
    """创建 Web API 应用。"""
    app_config = config or load_config()
    db = database or DatabaseManager(
        app_config.database.type,
        app_config.database.connection,
    )
    db.initialize_database()
    cache = TtlCache()

    app = FastAPI(title="GW Dashboard API", version="0.1.0")
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

    @app.get("/api/map/satellites")
    def map_satellites(
        at: str | None = Query(default=None, description="ISO-8601 UTC time"),
    ) -> Any:
        moment = _parse_time_query(at)
        cache_key = f"map:{moment.isoformat(timespec='seconds')}"
        return _cached(
            app,
            cache_key,
            lambda: build_map_satellites(db, at=moment),
            ttl_override=min(app_config.backend.cache_ttl_seconds, 10),
        )

    _mount_frontend(app, app_config)
    return app


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
    dist_dir = Path(config.frontend.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = Path.cwd() / dist_dir
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
