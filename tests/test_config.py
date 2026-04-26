from pathlib import Path

import pytest

from gw.config import (
    ConfigError,
    config_from_env,
    load_config,
    parse_startup_args,
    required_config_items,
)
from gw.main import load_startup_config


def test_loads_config_from_yaml_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
database:
  type: sqlite3
  connection: database/gw.sqlite3
backend:
  host: 0.0.0.0
  port: 9000
  cors_origins:
    - http://localhost:5173
    - https://dashboard.example.com
frontend:
  origin: https://dashboard.example.com
  dist_dir: frontend/dist
daemon:
  update_check_interval_seconds: 1800
  data_valid_duration_seconds: 43200
  satellite_record_limit: 500
scraper:
  network_timeout_seconds: 10
""",
        encoding="utf-8",
    )

    config = load_config(["-c", str(config_file)], env={})

    assert config.database.type == "sqlite3"
    assert config.database.connection == "database/gw.sqlite3"
    assert config.backend.host == "0.0.0.0"
    assert config.backend.port == 9000
    assert config.backend.reload is False
    assert config.backend.cors_origins == [
        "http://localhost:5173",
        "https://dashboard.example.com",
    ]
    assert config.frontend.origin == "https://dashboard.example.com"
    assert config.daemon.data_valid_duration_seconds == 43200
    assert config.daemon.satellite_record_limit == 500
    assert config.scraper.network_timeout_seconds == 10


def test_parse_startup_args_accepts_frontend_build_flag():
    args = parse_startup_args(["-d", "-c", "config.yaml"])

    assert args.build_frontend is True
    assert args.config_file == "config.yaml"


def test_loads_sqlite_config_from_environment_only():
    config = load_config(
        [],
        env={
            "GW_DATABASE_TYPE": "sqlite3",
            "GW_DATABASE_PATH": "database/env.sqlite3",
            "GW_BACKEND_PORT": "9100",
            "GW_BACKEND_CORS_ORIGINS": "http://localhost:5173,https://x.example",
        },
    )

    assert config.database.type == "sqlite3"
    assert config.database.connection == "database/env.sqlite3"
    assert config.backend.host == "127.0.0.1"
    assert config.backend.port == 9100
    assert config.backend.cors_origins == [
        "http://localhost:5173",
        "https://x.example",
    ]


def test_loads_server_database_connection_from_environment():
    config = load_config(
        [],
        env={
            "GW_DATABASE_TYPE": "pgsql",
            "GW_DATABASE_HOST": "db.local",
            "GW_DATABASE_PORT": "5433",
            "GW_DATABASE_USER": "gw",
            "GW_DATABASE_PASSWORD": "secret",
            "GW_DATABASE_NAME": "gw_dashboard",
        },
    )

    assert config.database.type == "pgsql"
    assert config.database.connection == {
        "host": "db.local",
        "port": "5433",
        "user": "gw",
        "password": "secret",
        "database": "gw_dashboard",
    }


def test_environment_overrides_yaml_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
database:
  type: sqlite3
  connection: database/file.sqlite3
backend:
  port: 8000
daemon:
  satellite_record_limit: 1000
""",
        encoding="utf-8",
    )

    config = load_config(
        ["--config", str(config_file)],
        env={
            "GW_DATABASE_CONNECTION": "database/env.sqlite3",
            "GW_BACKEND_PORT": "9900",
            "GW_DAEMON_SATELLITE_RECORD_LIMIT": "2000",
        },
    )

    assert config.database.type == "sqlite3"
    assert config.database.connection == "database/env.sqlite3"
    assert config.backend.port == 9900
    assert config.daemon.satellite_record_limit == 2000


def test_main_load_startup_config_uses_same_loader(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
database:
  type: sqlite3
  path: database/main.sqlite3
""",
        encoding="utf-8",
    )

    config = load_startup_config(["-c", str(config_file)], env={})

    assert config.database.connection == "database/main.sqlite3"


def test_missing_database_config_uses_default_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    config = load_config([], env={})

    assert config.database.type == "sqlite3"
    assert config.database.connection == str(
        Path(tmp_path, ".gwtracking", "database.db")
    )
    assert config.frontend.dist_dir == "gw/web/static"


def test_non_sqlite_database_requires_connection():
    with pytest.raises(ConfigError, match="database.connection"):
        load_config([], env={"GW_DATABASE_TYPE": "mysql"})


def test_invalid_yaml_root_raises_clear_error(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("- not\n- object\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="根节点"):
        load_config(["-c", str(config_file)], env={})


def test_invalid_integer_environment_value_raises_clear_error():
    with pytest.raises(ConfigError, match="backend.port"):
        load_config(
            [],
            env={
                "GW_DATABASE_TYPE": "sqlite3",
                "GW_DATABASE_PATH": "database/gw.sqlite3",
                "GW_BACKEND_PORT": "not-a-number",
            },
        )


def test_invalid_boolean_environment_value_raises_clear_error():
    with pytest.raises(ConfigError, match="backend.reload"):
        load_config(
            [],
            env={
                "GW_DATABASE_TYPE": "sqlite3",
                "GW_DATABASE_PATH": "database/gw.sqlite3",
                "GW_BACKEND_RELOAD": "maybe",
            },
        )


def test_reload_true_raises_clear_error():
    with pytest.raises(ConfigError, match="backend.reload 当前入口暂不支持"):
        load_config([], env={"GW_BACKEND_RELOAD": "true"})


def test_config_from_env_returns_only_present_values():
    assert config_from_env({}) == {}
    assert config_from_env({"GW_FRONTEND_ORIGIN": "https://x.example"}) == {
        "frontend": {"origin": "https://x.example"}
    }


def test_required_config_items_document_user_decisions():
    items = required_config_items()

    assert any("database.type" in item and "默认 sqlite3" in item for item in items)
    assert any(
        "database.connection" in item and "~/.gwtracking/database.db" in item
        for item in items
    )
    assert any("backend.reload" in item and "不支持 true" in item for item in items)
