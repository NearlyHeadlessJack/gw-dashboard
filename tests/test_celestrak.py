"""Tests for gw.scraper.celestrak — TLE parsing and fetching."""

import pytest
from gw.scraper import celestrak
from gw.scraper.celestrak import (
    CELESTRAK_URL,
    fetch_group_tle_data,
    fetch_tle,
    fetch_tle_data,
    parse_tle,
)


# ---- Sample TLE data ----

# Real TLE data for 星网低轨01组 (2024-240), first 3 satellites
SAMPLE_TLE = """\
HULIANWANG DIGUI-01
1 62323U 24240A   26115.49220466  .00000041  00000+0  60880-4 0  9996
2 62323  86.5040   1.0150 0001837  72.4834 287.6500 13.24413432 65663
HULIANWANG DIGUI-02
1 62324U 24240B   26115.49966838  .00000039  00000+0  57141-4 0  9990
2 62324  86.5069   1.1568 0001856  73.6881 286.4457 13.24412762 65679
HULIANWANG DIGUI-03
1 62325U 24240C   26115.48454868  .00000056  00000+0  96273-4 0  9993
2 62325  86.5022   0.9286 0001766  71.6719 288.4607 13.24412313 65661
"""

# Single satellite TLE
SINGLE_TLE = """\
ISS (ZARYA)
1 25544U 98067A   24123.12345678  .00016717  00000+0  30280-3 0  9999
2 25544  51.6412 200.2345 0006703  50.1234 310.0123 15.49560600405678
"""

# TLE with extra blank lines and whitespace
MESSY_TLE = """

HULIANWANG DIGUI-01
1 62323U 24240A   26115.49220466  .00000041  00000+0  60880-4 0  9996
2 62323  86.5040   1.0150 0001837  72.4834 287.6500 13.24413432 65663

HULIANWANG DIGUI-02
1 62324U 24240B   26115.49966838  .00000039  00000+0  57141-4 0  9990
2 62324  86.5069   1.1568 0001856  73.6881 286.4457 13.24412762 65679

"""

# Invalid TLE (no valid lines)
INVALID_TLE = "This is not TLE data\nNor is this\nOr this"

# TLE where line1 doesn't start with "1 "
BAD_LINE_TLE = """\
Some Satellite
X 25544U 98067A   24123.12345678  .00016717  00000+0  30280-3 0  9999
2 25544  51.6412 200.2345 0006703  50.1234 310.0123 15.49560600405678
"""


class StubResponse:
    def __init__(self, text="stub tle", error=None):
        self.text = text
        self.error = error
        self.raise_for_status_called = False

    def raise_for_status(self):
        self.raise_for_status_called = True
        if self.error is not None:
            raise self.error


class TestParseTle:
    def test_parses_multiple_satellites(self):
        result = parse_tle(SAMPLE_TLE)

        assert len(result) == 3
        assert result[0]["name"] == "HULIANWANG DIGUI-01"
        assert result[1]["name"] == "HULIANWANG DIGUI-02"
        assert result[2]["name"] == "HULIANWANG DIGUI-03"

    def test_parses_orbital_elements(self):
        result = parse_tle(SAMPLE_TLE)

        sat = result[0]
        assert sat["catalog_number"] == "62323"
        assert sat["intl_designator"] == "24240A"
        assert sat["epoch_year"] == 26
        assert abs(sat["epoch_day"] - 115.49220466) < 0.0001
        assert abs(sat["inclination"] - 86.504) < 0.01
        assert abs(sat["raan"] - 1.015) < 0.01
        assert abs(sat["eccentricity"] - 0.0001837) < 0.00001
        assert abs(sat["arg_perigee"] - 72.4834) < 0.01
        assert abs(sat["mean_anomaly"] - 287.65) < 0.01
        assert abs(sat["mean_motion"] - 13.24413432) < 0.0001

    def test_preserves_raw_lines(self):
        result = parse_tle(SAMPLE_TLE)

        assert result[0]["line1"].startswith("1 ")
        assert result[0]["line2"].startswith("2 ")

    def test_parses_single_satellite(self):
        result = parse_tle(SINGLE_TLE)

        assert len(result) == 1
        assert result[0]["name"] == "ISS (ZARYA)"
        assert result[0]["catalog_number"] == "25544"

    def test_handles_messy_whitespace(self):
        result = parse_tle(MESSY_TLE)

        assert len(result) == 2
        assert result[0]["name"] == "HULIANWANG DIGUI-01"
        assert result[1]["name"] == "HULIANWANG DIGUI-02"

    def test_returns_empty_for_invalid_data(self):
        result = parse_tle(INVALID_TLE)

        assert result == []

    def test_skips_bad_lines(self):
        result = parse_tle(BAD_LINE_TLE)

        # The "X" prefix line should be skipped
        assert result == []

    def test_second_satellite_values(self):
        result = parse_tle(SAMPLE_TLE)

        sat = result[1]
        assert sat["catalog_number"] == "62324"
        assert sat["intl_designator"] == "24240B"
        assert abs(sat["inclination"] - 86.5069) < 0.01


class TestFetchTle:
    def test_fetches_group_tle_with_intdes_param(self, monkeypatch):
        response = StubResponse(SAMPLE_TLE)
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return response

        monkeypatch.setattr(celestrak.requests, "get", fake_get)

        assert fetch_tle("2024-240") == SAMPLE_TLE
        assert calls == [(CELESTRAK_URL, {"params": {"INTDES": "2024-240"}})]
        assert response.raise_for_status_called

    def test_fetches_single_satellite_tle_with_intdes_param(self, monkeypatch):
        response = StubResponse(SINGLE_TLE)

        def fake_get(url, **kwargs):
            assert url == CELESTRAK_URL
            assert kwargs == {"params": {"INTDES": "2024-240A"}}
            return response

        monkeypatch.setattr(celestrak.requests, "get", fake_get)

        assert fetch_tle("2024-240A") == SINGLE_TLE
        assert response.raise_for_status_called

    def test_fetches_tle_with_custom_url_and_timeout(self, monkeypatch):
        response = StubResponse(SINGLE_TLE)

        def fake_get(url, **kwargs):
            assert url == "https://tle.example/gp.php"
            assert kwargs == {"params": {"INTDES": "2024-240A"}, "timeout": 5}
            return response

        monkeypatch.setattr(celestrak.requests, "get", fake_get)

        assert fetch_tle("2024-240A", url="https://tle.example/gp.php", timeout=5)
        assert response.raise_for_status_called

    def test_raises_on_http_errors(self, monkeypatch):
        response = StubResponse(error=RuntimeError("bad status"))
        monkeypatch.setattr(celestrak.requests, "get", lambda *args, **kwargs: response)

        with pytest.raises(RuntimeError, match="bad status"):
            fetch_tle("INVALID-ID")

        assert response.raise_for_status_called


class TestFetchTleData:
    def test_returns_parsed_satellite_data(self, monkeypatch):
        monkeypatch.setattr(celestrak, "fetch_tle", lambda intl_designator: SAMPLE_TLE)

        result = fetch_tle_data("2024-240")

        assert len(result) == 3
        assert result[0]["name"] == "HULIANWANG DIGUI-01"
        assert "inclination" in result[0]
        assert abs(result[0]["inclination"] - 86.5) < 2  # Low orbit, should be ~86.5°


class TestFetchGroupTleData:
    def test_returns_first_n_objects_sorted_by_intl_designator_piece(self, monkeypatch):
        calls = []
        parsed = [
            {"name": "ROCKET BODY", "intl_designator": "24240D"},
            {"name": "HULIANWANG DIGUI-03", "intl_designator": "24240C"},
            {"name": "HULIANWANG DIGUI-01", "intl_designator": "24240A"},
            {"name": "HULIANWANG DIGUI-02", "intl_designator": "24240B"},
        ]

        def fake_fetch_tle(intl_designator):
            calls.append(intl_designator)
            return "raw tle"

        monkeypatch.setattr(celestrak, "fetch_tle", fake_fetch_tle)
        monkeypatch.setattr(celestrak, "parse_tle", lambda tle_text: parsed)

        result = fetch_group_tle_data("2024-240", 3)

        assert calls == ["2024-240"]
        assert [item["intl_designator"] for item in result] == [
            "24240A",
            "24240B",
            "24240C",
        ]
        assert "ROCKET BODY" not in [item["name"] for item in result]

    def test_sorts_multi_letter_pieces_after_single_letter_sequence(self, monkeypatch):
        parsed = [
            {"name": "OBJECT AA", "intl_designator": "24240AA"},
            {"name": "OBJECT B", "intl_designator": "24240B"},
            {"name": "OBJECT Z", "intl_designator": "24240Z"},
            {"name": "OBJECT A", "intl_designator": "24240A"},
        ]

        monkeypatch.setattr(celestrak, "fetch_tle", lambda intl_designator: "raw tle")
        monkeypatch.setattr(celestrak, "parse_tle", lambda tle_text: parsed)

        result = fetch_group_tle_data("2024-240", 4)

        assert [item["intl_designator"] for item in result] == [
            "24240A",
            "24240B",
            "24240Z",
            "24240AA",
        ]

    def test_accepts_full_year_designators_in_parsed_data(self, monkeypatch):
        parsed = [
            {"name": "OBJECT C", "intl_designator": "2024-240C"},
            {"name": "OBJECT A", "intl_designator": "2024-240A"},
            {"name": "OBJECT B", "intl_designator": "2024-240B"},
        ]

        monkeypatch.setattr(celestrak, "fetch_tle", lambda intl_designator: "raw tle")
        monkeypatch.setattr(celestrak, "parse_tle", lambda tle_text: parsed)

        result = fetch_group_tle_data("2024-240", 2)

        assert [item["intl_designator"] for item in result] == [
            "2024-240A",
            "2024-240B",
        ]

    def test_zero_count_returns_empty_without_fetching(self, monkeypatch):
        monkeypatch.setattr(
            celestrak,
            "fetch_tle",
            lambda intl_designator: (_ for _ in ()).throw(AssertionError("fetched")),
        )

        assert fetch_group_tle_data("2024-240", 0) == []

    def test_rejects_negative_satellite_count(self):
        with pytest.raises(ValueError, match="不能为负数"):
            fetch_group_tle_data("2024-240", -1)
