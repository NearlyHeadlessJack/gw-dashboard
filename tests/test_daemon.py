import threading
import logging

from gw.config import AppConfig, DaemonConfig, DatabaseConfig
from gw.daemon import DaemonCycleResult, DashboardDaemon


class FakeDatabase:
    def __init__(self, expired_states):
        self.expired_states = list(expired_states)
        self.check_count = 0

    def is_update_expired(self):
        self.check_count += 1
        if self.expired_states:
            return self.expired_states.pop(0)
        return False


def make_config(interval=60):
    return AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        daemon=DaemonConfig(update_check_interval_seconds=interval),
    )


def test_start_runtime_services_only_runs_once():
    calls = []
    daemon = DashboardDaemon(
        make_config(),
        FakeDatabase([False]),
        web_server_starter=lambda: calls.append("web"),
        frontend_server_starter=lambda: calls.append("frontend"),
    )

    daemon.start_runtime_services()
    daemon.start_runtime_services()

    assert calls == ["web", "frontend"]


def test_run_cycle_sleeps_without_update_when_database_not_expired():
    update_calls = []
    database = FakeDatabase([False])
    daemon = DashboardDaemon(
        make_config(),
        database,
        data_updater=lambda: update_calls.append("update"),
    )

    result = daemon.run_cycle()

    assert result == DaemonCycleResult(
        expired_before_update=False,
        update_ran=False,
        expired_after_update=False,
    )
    assert update_calls == []
    assert database.check_count == 1


def test_run_cycle_updates_then_rechecks_database_expiration():
    update_calls = []
    database = FakeDatabase([True, False])
    daemon = DashboardDaemon(
        make_config(),
        database,
        data_updater=lambda: update_calls.append("update"),
    )

    result = daemon.run_cycle()

    assert result == DaemonCycleResult(
        expired_before_update=True,
        update_ran=True,
        expired_after_update=False,
    )
    assert update_calls == ["update"]
    assert database.check_count == 2


def test_run_cycle_logs_update_status(caplog):
    database = FakeDatabase([True, False])
    daemon = DashboardDaemon(
        make_config(),
        database,
        data_updater=lambda: None,
    )

    with caplog.at_level(logging.INFO, logger="gw.daemon.runner"):
        daemon.run_cycle()

    messages = [record.getMessage() for record in caplog.records]
    assert "daemon cycle checking data expiration" in messages
    assert "daemon cycle detected expired data; update starting" in messages
    assert "daemon cycle complete: data update finished successfully" in messages


def test_run_cycle_reports_still_expired_after_update_placeholder():
    database = FakeDatabase([True, True])
    daemon = DashboardDaemon(make_config(), database)

    result = daemon.run_cycle()

    assert result.expired_before_update is True
    assert result.update_ran is True
    assert result.expired_after_update is True


def test_daemon_runs_as_thread_and_stop_wakes_sleep():
    calls = []
    checked = threading.Event()

    class ThreadDatabase:
        def is_update_expired(self):
            checked.set()
            return False

    daemon = DashboardDaemon(
        make_config(interval=60),
        ThreadDatabase(),
        web_server_starter=lambda: calls.append("web"),
        frontend_server_starter=lambda: calls.append("frontend"),
    )

    daemon.start()
    assert checked.wait(timeout=1)
    daemon.stop()
    daemon.join(timeout=1)

    assert daemon.is_alive() is False
    assert calls == ["web", "frontend"]
    assert daemon.last_cycle_result == DaemonCycleResult(False, False, False)


def test_daemon_updates_initial_data_before_starting_runtime_services():
    calls = []
    services_ready = threading.Event()
    database = FakeDatabase([True, False])

    daemon = DashboardDaemon(
        make_config(interval=60),
        database,
        web_server_starter=lambda: calls.append("web"),
        frontend_server_starter=lambda: (
            calls.append("frontend") or services_ready.set()
        ),
        data_updater=lambda: calls.append("update"),
    )

    daemon.start()
    assert services_ready.wait(timeout=1)
    daemon.stop()
    daemon.join(timeout=1)

    assert daemon.is_alive() is False
    assert calls == ["update", "web", "frontend"]
    assert daemon.last_cycle_result == DaemonCycleResult(True, True, False)


def test_daemon_does_not_start_runtime_services_when_initial_update_stays_expired():
    calls = []
    database = FakeDatabase([True, True])
    daemon = DashboardDaemon(
        make_config(interval=60),
        database,
        web_server_starter=lambda: calls.append("web"),
        frontend_server_starter=lambda: calls.append("frontend"),
        data_updater=lambda: calls.append("update"),
    )

    daemon.start()
    daemon.join(timeout=1)

    assert daemon.is_alive() is False
    assert calls == ["update"]
    assert isinstance(daemon.last_error, RuntimeError)
    assert daemon.last_cycle_result == DaemonCycleResult(True, True, True)
