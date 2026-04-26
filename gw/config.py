"""启动配置加载。

支持从 YAML 文件和环境变量读取配置；环境变量优先级高于 YAML。
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


ConfigMapping = dict[str, Any]
DEFAULT_DATABASE_TYPE = "sqlite3"
DEFAULT_DATABASE_PATH = "~/.gwtracking/database.db"

REQUIRED_CONFIG_ITEMS = [
    "database.type: 默认 sqlite3，可选 sqlite3/mysql/pgsql",
    "database.connection: 默认 ~/.gwtracking/database.db；sqlite3 文件路径，或 mysql/pgsql SQLAlchemy URL/dict",
    "backend.host: 后端 web 服务监听地址，默认 127.0.0.1",
    "backend.port: 后端 web 服务监听端口，默认 8000",
    "backend.reload: 默认 false；当前入口暂不支持 true",
    "backend.cors_origins: 允许访问后端 API 的前端来源列表",
    "backend.cache_ttl_seconds: web API 缓存时间，默认 30",
    "frontend.origin: 前端页面来源，默认 http://localhost:5173",
    "frontend.dist_dir: 前端构建产物目录，默认 gw/web/static（随 Python 包发布）",
    "daemon.update_check_interval_seconds: 守护进程检查更新间隔，默认 3600",
    "daemon.data_valid_duration_seconds: 数据有效期，默认 86400",
    "daemon.satellite_record_limit: 单星历史记录上限，默认 1000",
    "scraper.network_timeout_seconds: 爬虫网络超时，默认 30",
    "scraper.huiji_url: 灰机 wiki 地址，可选",
    "scraper.celestrak_url: Celestrak 地址，可选",
]


class ConfigError(ValueError):
    """启动配置无效。"""


def default_database_path() -> str:
    """返回默认 SQLite 数据库路径。"""
    return str(Path(DEFAULT_DATABASE_PATH).expanduser())


@dataclass(frozen=True)
class DatabaseConfig:
    type: str = DEFAULT_DATABASE_TYPE
    connection: str | dict[str, Any] = field(default_factory=default_database_path)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DatabaseConfig":
        db_type = str(
            data.get("type") or data.get("db_type") or DEFAULT_DATABASE_TYPE
        ).strip()
        if not db_type:
            raise ConfigError("缺少必填配置 database.type")

        connection = _database_connection_from_mapping(data)
        if connection is None:
            if db_type.strip().lower() in {"sqlite", "sqlite3"}:
                connection = default_database_path()
            else:
                raise ConfigError("缺少必填配置 database.connection")

        return cls(type=db_type, connection=connection)


@dataclass(frozen=True)
class BackendConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    cache_ttl_seconds: int = 30

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BackendConfig":
        reload = _as_bool(data.get("reload", cls.reload), "backend.reload")
        if reload:
            raise ConfigError("backend.reload 当前入口暂不支持 true，请保持 false")
        return cls(
            host=str(data.get("host", cls.host)),
            port=_as_int(data.get("port", cls.port), "backend.port"),
            reload=reload,
            cors_origins=_as_str_list(
                data.get("cors_origins", ["http://localhost:5173"]),
                "backend.cors_origins",
            ),
            cache_ttl_seconds=_as_int(
                data.get("cache_ttl_seconds", cls.cache_ttl_seconds),
                "backend.cache_ttl_seconds",
            ),
        )


@dataclass(frozen=True)
class FrontendConfig:
    origin: str = "http://localhost:5173"
    dist_dir: str = "gw/web/static"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "FrontendConfig":
        return cls(
            origin=str(data.get("origin", cls.origin)),
            dist_dir=str(data.get("dist_dir", cls.dist_dir)),
        )


@dataclass(frozen=True)
class DaemonConfig:
    update_check_interval_seconds: int = 3600
    data_valid_duration_seconds: int = 86400
    satellite_record_limit: int | None = 1000

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "DaemonConfig":
        satellite_record_limit = data.get(
            "satellite_record_limit",
            cls.satellite_record_limit,
        )
        return cls(
            update_check_interval_seconds=_as_int(
                data.get(
                    "update_check_interval_seconds",
                    cls.update_check_interval_seconds,
                ),
                "daemon.update_check_interval_seconds",
            ),
            data_valid_duration_seconds=_as_int(
                data.get("data_valid_duration_seconds", cls.data_valid_duration_seconds),
                "daemon.data_valid_duration_seconds",
            ),
            satellite_record_limit=(
                None
                if satellite_record_limit is None
                else _as_int(satellite_record_limit, "daemon.satellite_record_limit")
            ),
        )


@dataclass(frozen=True)
class ScraperConfig:
    huiji_url: str | None = None
    celestrak_url: str | None = None
    network_timeout_seconds: int = 30

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ScraperConfig":
        return cls(
            huiji_url=_as_optional_str(data.get("huiji_url")),
            celestrak_url=_as_optional_str(data.get("celestrak_url")),
            network_timeout_seconds=_as_int(
                data.get("network_timeout_seconds", cls.network_timeout_seconds),
                "scraper.network_timeout_seconds",
            ),
        )


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig
    backend: BackendConfig = field(default_factory=BackendConfig)
    frontend: FrontendConfig = field(default_factory=FrontendConfig)
    daemon: DaemonConfig = field(default_factory=DaemonConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AppConfig":
        database_data = _section(data, "database")
        return cls(
            database=DatabaseConfig.from_mapping(database_data),
            backend=BackendConfig.from_mapping(_section(data, "backend")),
            frontend=FrontendConfig.from_mapping(_section(data, "frontend")),
            daemon=DaemonConfig.from_mapping(_section(data, "daemon")),
            scraper=ScraperConfig.from_mapping(_section(data, "scraper")),
        )


def parse_startup_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析启动参数。"""
    parser = argparse.ArgumentParser(prog="gw-dashboard")
    parser.add_argument(
        "-c",
        "--config",
        dest="config_file",
        help="YAML 配置文件路径",
    )
    parser.add_argument(
        "-d",
        "--build-frontend",
        action="store_true",
        help="启动前重新编译 frontend 前端静态资源（需要 Node.js/npm 和源码目录）",
    )
    return parser.parse_args(argv)


def load_config(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    """从 `-c` 指定 YAML 和环境变量加载启动配置。"""
    args = parse_startup_args(argv)
    config_data: ConfigMapping = {}

    if args.config_file:
        config_data = load_yaml_config(args.config_file)

    env_data = config_from_env(os.environ if env is None else env)
    merged = _deep_merge(config_data, env_data)
    return AppConfig.from_mapping(merged)


def load_yaml_config(path: str | Path) -> ConfigMapping:
    """读取 YAML 配置文件。"""
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"无法读取配置文件: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件不是有效 YAML: {config_path}") from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError("YAML 配置根节点必须是对象")
    return dict(raw)


def config_from_env(env: Mapping[str, str]) -> ConfigMapping:
    """从 GW_ 环境变量构造配置片段。"""
    data: ConfigMapping = {}

    _set_if_present(data, ("database", "type"), env, "GW_DATABASE_TYPE")
    _set_database_connection_env(data, env)

    _set_if_present(data, ("backend", "host"), env, "GW_BACKEND_HOST")
    _set_if_present(data, ("backend", "port"), env, "GW_BACKEND_PORT")
    _set_if_present(data, ("backend", "reload"), env, "GW_BACKEND_RELOAD")
    _set_if_present(data, ("backend", "cors_origins"), env, "GW_BACKEND_CORS_ORIGINS")
    _set_if_present(
        data,
        ("backend", "cache_ttl_seconds"),
        env,
        "GW_BACKEND_CACHE_TTL_SECONDS",
    )

    _set_if_present(data, ("frontend", "origin"), env, "GW_FRONTEND_ORIGIN")
    _set_if_present(data, ("frontend", "dist_dir"), env, "GW_FRONTEND_DIST_DIR")

    _set_if_present(
        data,
        ("daemon", "update_check_interval_seconds"),
        env,
        "GW_DAEMON_UPDATE_CHECK_INTERVAL_SECONDS",
    )
    _set_if_present(
        data,
        ("daemon", "data_valid_duration_seconds"),
        env,
        "GW_DAEMON_DATA_VALID_DURATION_SECONDS",
    )
    _set_if_present(
        data,
        ("daemon", "satellite_record_limit"),
        env,
        "GW_DAEMON_SATELLITE_RECORD_LIMIT",
    )

    _set_if_present(data, ("scraper", "huiji_url"), env, "GW_SCRAPER_HUIJI_URL")
    _set_if_present(
        data,
        ("scraper", "celestrak_url"),
        env,
        "GW_SCRAPER_CELESTRAK_URL",
    )
    _set_if_present(
        data,
        ("scraper", "network_timeout_seconds"),
        env,
        "GW_SCRAPER_NETWORK_TIMEOUT_SECONDS",
    )

    return data


def required_config_items() -> list[str]:
    """返回启动前用户必须确定的配置项说明。"""
    return list(REQUIRED_CONFIG_ITEMS)


def _database_connection_from_mapping(data: Mapping[str, Any]) -> str | dict[str, Any] | None:
    if data.get("connection") is not None:
        return data["connection"]
    if data.get("path") is not None:
        return str(data["path"])

    connection: dict[str, Any] = {}
    for key in ("driver", "host", "port", "username", "user", "password"):
        if data.get(key) is not None:
            connection[key] = data[key]
    for key in ("database", "dbname", "db"):
        if data.get(key) is not None:
            connection["database"] = data[key]
            break
    return connection or None


def _set_database_connection_env(data: ConfigMapping, env: Mapping[str, str]) -> None:
    if "GW_DATABASE_CONNECTION" in env:
        _set_nested(data, ("database", "connection"), env["GW_DATABASE_CONNECTION"])
        return
    if "GW_DATABASE_PATH" in env:
        _set_nested(data, ("database", "connection"), env["GW_DATABASE_PATH"])
        return

    connection: dict[str, str] = {}
    env_to_key = {
        "GW_DATABASE_DRIVER": "driver",
        "GW_DATABASE_HOST": "host",
        "GW_DATABASE_PORT": "port",
        "GW_DATABASE_USERNAME": "username",
        "GW_DATABASE_USER": "user",
        "GW_DATABASE_PASSWORD": "password",
        "GW_DATABASE_NAME": "database",
        "GW_DATABASE_DB": "database",
    }
    for env_name, key in env_to_key.items():
        if env_name in env:
            connection[key] = env[env_name]
    if connection:
        _set_nested(data, ("database", "connection"), connection)


def _set_if_present(
    data: ConfigMapping,
    path: tuple[str, ...],
    env: Mapping[str, str],
    env_name: str,
) -> None:
    if env_name in env:
        _set_nested(data, path, env[env_name])


def _set_nested(data: ConfigMapping, path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        current = current.setdefault(key, {})
    current[path[-1]] = value


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> ConfigMapping:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"{name} 配置必须是对象")
    return value


def _as_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field_name} 必须是整数") from exc


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"{field_name} 必须是布尔值")


def _as_str_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise ConfigError(f"{field_name} 必须是字符串列表或逗号分隔字符串")


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
