from datetime import datetime, timezone

import pytest

from gw.orbit import (
    OrbitPropagationError,
    generate_ground_track,
    propagate_tle_position,
)


RAW_TLE = """\
HULIANWANG DIGUI-01
1 62323U 24240A   26115.49220466  .00000041  00000+0  60880-4 0  9996
2 62323  86.5040   1.0150 0001837  72.4834 287.6500 13.24413432 65663
"""


def test_propagate_tle_position_returns_geodetic_position():
    position = propagate_tle_position(
        RAW_TLE,
        datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
    )

    assert -90 <= position["latitude"] <= 90
    assert -180 <= position["longitude"] <= 180
    assert 900 <= position["altitude_km"] <= 1300


def test_generate_ground_track_returns_ordered_points():
    track = generate_ground_track(
        RAW_TLE,
        datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
        minutes_before=10,
        minutes_after=10,
        step_minutes=5,
    )

    assert len(track) == 5
    assert track[0]["timestamp"] == "2026-04-26T07:50:00Z"
    assert track[-1]["timestamp"] == "2026-04-26T08:10:00Z"
    assert all(-90 <= point["latitude"] <= 90 for point in track)
    assert all(-180 <= point["longitude"] <= 180 for point in track)


def test_propagate_tle_position_rejects_invalid_tle():
    with pytest.raises(OrbitPropagationError, match="缺少 TLE"):
        propagate_tle_position("not a tle")
