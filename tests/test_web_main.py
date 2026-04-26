import logging

from gw.config import AppConfig, BackendConfig, DatabaseConfig, FrontendConfig
from gw.web import __main__ as web_main


def test_frontend_entry_url_uses_loopback_for_wildcard_host():
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="0.0.0.0", port=8123),
    )

    assert web_main.frontend_entry_url(config) == "http://127.0.0.1:8123"


def test_frontend_entry_url_wraps_ipv6_host():
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="::1", port=8123),
    )

    assert web_main.frontend_entry_url(config) == "http://[::1]:8123"


def test_database_connection_for_log_masks_password():
    assert web_main.database_connection_for_log(
        {
            "host": "db.local",
            "user": "gw",
            "password": "secret",
            "database": "gw",
        }
    ) == {
        "host": "db.local",
        "user": "gw",
        "password": "***",
        "database": "gw",
    }


def test_main_logs_frontend_entry_url_and_runs_uvicorn(monkeypatch, caplog):
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="0.0.0.0", port=8123),
        frontend=FrontendConfig(dist_dir="frontend/dist"),
    )
    calls = {}

    monkeypatch.setattr(web_main, "configure_console_logging", lambda: None)
    monkeypatch.setattr(web_main, "load_config", lambda argv: config)
    monkeypatch.setattr(web_main, "create_app", lambda loaded_config: "app")
    monkeypatch.setattr(
        web_main.uvicorn,
        "run",
        lambda app, **kwargs: calls.update({"app": app, **kwargs}),
    )

    with caplog.at_level(logging.INFO):
        web_main.main(["--config", "config.yaml"])

    assert "frontend entry URL: http://127.0.0.1:8123" in caplog.text
    assert "database configured: type=sqlite3 connection=:memory:" in caplog.text
    assert calls["app"] == "app"
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 8123
    assert calls["reload"] is False
