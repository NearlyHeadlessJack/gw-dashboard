from __future__ import annotations

import pytest

from gw.web.time_service import NTP_EPOCH_OFFSET_SECONDS, NtpTimeService


class FakeNtpSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.timeout: float | None = None
        self.sent_to: tuple[str, int] | None = None

    def __enter__(self) -> "FakeNtpSocket":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def sendto(self, packet: bytes, address: tuple[str, int]) -> None:
        assert len(packet) == 48
        assert packet[0] == 0x1B
        self.sent_to = address

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        assert size == 48
        return self.response, ("ntp2.aliyun.com", 123)


def test_ntp_time_service_reads_ntp2_aliyun_time():
    fake_socket = FakeNtpSocket(_ntp_response(1_000.4))
    time_values = iter([1_000.0, 1_000.2, 1_000.5])
    service = NtpTimeService(
        socket_factory=lambda *_args: fake_socket,
        time_func=lambda: next(time_values),
        monotonic_func=lambda: 10.0,
    )

    snapshot = service.current_time()

    assert fake_socket.sent_to == ("ntp2.aliyun.com", 123)
    assert fake_socket.timeout == 2.0
    assert snapshot.server == "ntp2.aliyun.com"
    assert snapshot.offset_seconds == pytest.approx(0.3)
    assert snapshot.round_trip_seconds == pytest.approx(0.2)
    assert snapshot.utc.timestamp() == pytest.approx(1_000.8)
    assert snapshot.cached is False


def test_ntp_time_service_uses_cached_offset_when_resync_fails():
    calls = {"count": 0}

    def socket_factory(*_args: object) -> FakeNtpSocket:
        calls["count"] += 1
        if calls["count"] > 1:
            raise OSError("network unavailable")
        return FakeNtpSocket(_ntp_response(1_000.4))

    time_values = iter([1_000.0, 1_000.2, 1_000.5, 1_010.0])
    monotonic_values = iter([10.0, 20.0])
    service = NtpTimeService(
        sync_interval_seconds=1,
        socket_factory=socket_factory,
        time_func=lambda: next(time_values),
        monotonic_func=lambda: next(monotonic_values),
    )

    first = service.current_time()
    second = service.current_time()

    assert first.cached is False
    assert second.cached is True
    assert second.utc.timestamp() == pytest.approx(1_010.3)


def _ntp_response(unix_timestamp: float) -> bytes:
    ntp_timestamp = unix_timestamp + NTP_EPOCH_OFFSET_SECONDS
    seconds = int(ntp_timestamp)
    fraction = int((ntp_timestamp - seconds) * 2**32)
    packet = bytearray(48)
    packet[40:44] = seconds.to_bytes(4, "big")
    packet[44:48] = fraction.to_bytes(4, "big")
    return bytes(packet)
