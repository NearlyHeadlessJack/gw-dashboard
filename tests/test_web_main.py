import asyncio
import logging

from gw.config import AppConfig, BackendConfig, DatabaseConfig, FrontendConfig
from gw.web import __main__ as web_main
from gw.web import runtime


def test_frontend_entry_url_uses_loopback_for_wildcard_host():
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="0.0.0.0", port=8123),
    )

    assert runtime.frontend_entry_url(config) == "http://127.0.0.1:8123"


def test_frontend_entry_url_wraps_ipv6_host():
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="::1", port=8123),
    )

    assert runtime.frontend_entry_url(config) == "http://[::1]:8123"


def test_database_connection_for_log_masks_password():
    assert runtime.database_connection_for_log(
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


def test_main_logs_config_and_runs_uvicorn(monkeypatch, caplog):
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="0.0.0.0", port=8123),
        frontend=FrontendConfig(dist_dir="frontend/dist"),
    )
    calls = {}

    monkeypatch.setattr(web_main, "configure_console_logging", lambda: None)
    monkeypatch.setattr(web_main, "load_config", lambda argv: config)
    monkeypatch.setattr(
        web_main,
        "run_web_server",
        lambda loaded_config, logger: calls.update(
            {"config": loaded_config, "logger": logger.name}
        ),
    )

    with caplog.at_level(logging.INFO):
        web_main.main(["--config", "config.yaml"])

    assert "database configured: type=sqlite3 connection=:memory:" in caplog.text
    assert calls["config"] is config
    assert calls["logger"] == "gw.web.__main__"


def test_run_web_server_prints_frontend_entry_after_server_starts(monkeypatch):
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(host="0.0.0.0", port=8123),
    )
    events = []

    class FakeConfig:
        def __init__(self, app, **kwargs):
            self.app = app
            self.reload = kwargs["reload"]
            events.append(("config", app, kwargs))

    class FakeServer:
        started = False

        def __init__(self, server_config, *, on_started):
            self.server_config = server_config
            self.on_started = on_started

        def run(self):
            events.append("server.started")
            self.started = True
            self.on_started()

    monkeypatch.setattr(
        web_main,
        "create_app",
        lambda loaded_config, **kwargs: events.append(
            ("create_app", loaded_config, kwargs)
        )
        or "app",
    )
    monkeypatch.setattr(web_main.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(web_main, "FrontendEntryServer", FakeServer)
    monkeypatch.setattr(
        web_main,
        "log_frontend_entry",
        lambda logger, loaded_config: events.append(("frontend", loaded_config)),
    )

    web_main.run_web_server(config, logging.getLogger("test"))

    assert events == [
        ("create_app", config, {"log_frontend_on_startup": False}),
        (
            "config",
            "app",
            {
                "host": "0.0.0.0",
                "port": 8123,
                "reload": False,
                "log_config": None,
            },
        ),
        "server.started",
        ("frontend", config),
    ]


def test_run_web_server_rejects_reload_with_direct_app(monkeypatch):
    config = AppConfig(
        database=DatabaseConfig(connection=":memory:"),
        backend=BackendConfig(reload=True),
    )

    class FakeConfig:
        def __init__(self, app, **kwargs):
            self.app = app
            self.reload = kwargs["reload"]

    monkeypatch.setattr(
        web_main,
        "create_app",
        lambda loaded_config, **kwargs: object(),
    )
    monkeypatch.setattr(web_main.uvicorn, "Config", FakeConfig)

    try:
        web_main.run_web_server(config, logging.getLogger("test"))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("SystemExit was not raised")


def test_frontend_entry_server_notifies_after_uvicorn_startup(monkeypatch):
    events = []

    async def fake_startup(self, sockets=None):
        events.append("uvicorn.startup")
        self.started = True

    monkeypatch.setattr(web_main.uvicorn.Server, "startup", fake_startup)
    server_config = web_main.uvicorn.Config(lambda scope, receive, send: None)
    server = web_main.FrontendEntryServer(
        server_config,
        on_started=lambda: events.append("frontend.entry"),
    )

    asyncio.run(server.startup())

    assert events == ["uvicorn.startup", "frontend.entry"]
