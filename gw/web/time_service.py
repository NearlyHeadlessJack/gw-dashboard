"""NTP time source used by the web frontend."""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol


NTP_EPOCH_OFFSET_SECONDS = 2_208_988_800
NTP_PACKET_SIZE = 48
DEFAULT_NTP_SERVER = "ntp2.aliyun.com"


class NtpTimeError(RuntimeError):
    """Raised when the NTP source cannot provide a usable time."""


@dataclass(frozen=True)
class NtpTimeSnapshot:
    """Current UTC time derived from the NTP offset."""

    utc: datetime
    server: str
    offset_seconds: float
    round_trip_seconds: float | None
    synced_at: datetime
    cached: bool = False


class TimeService(Protocol):
    """Interface used by the FastAPI app for dependency injection in tests."""

    def current_time(self) -> NtpTimeSnapshot:
        """Return the current UTC time snapshot."""


class NtpTimeService:
    """Caches a local clock offset from an NTP server."""

    def __init__(
        self,
        *,
        server: str = DEFAULT_NTP_SERVER,
        port: int = 123,
        timeout_seconds: float = 2.0,
        sync_interval_seconds: float = 300.0,
        socket_factory: Callable[..., socket.socket] = socket.socket,
        time_func: Callable[[], float] = time.time,
        monotonic_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.server = server
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.sync_interval_seconds = sync_interval_seconds
        self._socket_factory = socket_factory
        self._time_func = time_func
        self._monotonic_func = monotonic_func
        self._offset_seconds: float | None = None
        self._round_trip_seconds: float | None = None
        self._synced_monotonic: float | None = None
        self._synced_at: datetime | None = None

    def current_time(self) -> NtpTimeSnapshot:
        """Return current UTC time using a cached NTP offset."""
        cached = True
        if self._should_sync():
            try:
                self._sync()
                cached = False
            except (OSError, NtpTimeError) as exc:
                if self._offset_seconds is None:
                    raise NtpTimeError(
                        f"无法从 {self.server} 获取标准时间"
                    ) from exc

        if self._offset_seconds is None or self._synced_at is None:
            raise NtpTimeError(f"无法从 {self.server} 获取标准时间")

        utc = datetime.fromtimestamp(
            self._time_func() + self._offset_seconds,
            tz=timezone.utc,
        )
        return NtpTimeSnapshot(
            utc=utc,
            server=self.server,
            offset_seconds=self._offset_seconds,
            round_trip_seconds=self._round_trip_seconds,
            synced_at=self._synced_at,
            cached=cached,
        )

    def _should_sync(self) -> bool:
        if self._offset_seconds is None or self._synced_monotonic is None:
            return True
        return (
            self._monotonic_func() - self._synced_monotonic
            >= self.sync_interval_seconds
        )

    def _sync(self) -> None:
        packet = bytearray(NTP_PACKET_SIZE)
        packet[0] = 0x1B

        with self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(self.timeout_seconds)
            started_at = self._time_func()
            client.sendto(bytes(packet), (self.server, self.port))
            response, _address = client.recvfrom(NTP_PACKET_SIZE)
            finished_at = self._time_func()

        if len(response) < NTP_PACKET_SIZE:
            raise NtpTimeError(f"{self.server} 返回的 NTP 数据不完整")

        transmit_time = _read_ntp_timestamp(response, 40)
        midpoint = (started_at + finished_at) / 2
        self._offset_seconds = transmit_time - midpoint
        self._round_trip_seconds = max(0.0, finished_at - started_at)
        self._synced_monotonic = self._monotonic_func()
        self._synced_at = datetime.fromtimestamp(
            transmit_time,
            tz=timezone.utc,
        )


def ntp_snapshot_to_payload(snapshot: NtpTimeSnapshot) -> dict[str, object]:
    """Serialize a time snapshot for the frontend."""
    return {
        "utc_time": _format_utc(snapshot.utc),
        "source": "ntp",
        "server": snapshot.server,
        "offset_seconds": snapshot.offset_seconds,
        "round_trip_seconds": snapshot.round_trip_seconds,
        "synced_at": _format_utc(snapshot.synced_at),
        "cached": snapshot.cached,
    }


def _read_ntp_timestamp(packet: bytes, offset: int) -> float:
    seconds = int.from_bytes(packet[offset : offset + 4], "big")
    fraction = int.from_bytes(packet[offset + 4 : offset + 8], "big")
    return seconds - NTP_EPOCH_OFFSET_SECONDS + fraction / 2**32


def _format_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
