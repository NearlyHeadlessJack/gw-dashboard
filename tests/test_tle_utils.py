from datetime import timezone

import pytest

from gw.utils import (
    TleParseError,
    calculate_tle_checksum,
    calculate_tle_orbit_elements,
    parse_tle,
)


NOAA_14_TLE = """\
NOAA 14
1 23455U 94089A   97320.90946019  .00000140  00000-0  10191-3 0  2621
2 23455  99.0090 272.6745 0008546 223.1686 136.8816 14.11711747148495
"""

ISS_TLE_WITHOUT_NAME = """\
1 25544U 98067A   26059.50000000  .00016717  00000-0  10270-3 0  9993
2 25544  51.6400 123.0010 0005000  90.0000 270.0000 15.50000000000000
"""


def test_parse_tle_decodes_fixed_width_fields():
    result = parse_tle(NOAA_14_TLE)

    assert result["name"] == "NOAA 14"
    assert result["catalog_number"] == "23455"
    assert result["classification"] == "U"
    assert result["intl_designator"] == "94089A"
    assert result["international_designator"] == "1994-089A"
    assert result["international_designator_year"] == 1994
    assert result["international_designator_launch_number"] == 89
    assert result["international_designator_piece"] == "A"
    assert result["epoch_year"] == 97
    assert result["epoch_full_year"] == 1997
    assert result["epoch_day"] == pytest.approx(320.90946019)
    assert result["mean_motion_first_derivative"] == pytest.approx(0.00000140)
    assert result["mean_motion_second_derivative"] == 0.0
    assert result["bstar"] == pytest.approx(0.00010191)
    assert result["ephemeris_type"] == 0
    assert result["element_number"] == 262
    assert result["inclination_deg"] == pytest.approx(99.0090)
    assert result["raan_deg"] == pytest.approx(272.6745)
    assert result["eccentricity"] == pytest.approx(0.0008546)
    assert result["argument_of_perigee_deg"] == pytest.approx(223.1686)
    assert result["mean_anomaly_deg"] == pytest.approx(136.8816)
    assert result["mean_motion_rev_per_day"] == pytest.approx(14.11711747)
    assert result["revolution_number_at_epoch"] == 14849
    assert result["status"] == "有效"
    assert result["raw_tle"] == "\n".join(
        [
            "NOAA 14",
            "1 23455U 94089A   97320.90946019  .00000140  00000-0  10191-3 0  2621",
            "2 23455  99.0090 272.6745 0008546 223.1686 136.8816 14.11711747148495",
        ]
    )


def test_parse_tle_converts_epoch_to_utc_datetime():
    result = parse_tle(NOAA_14_TLE)

    assert result["epoch_at"].tzinfo is timezone.utc
    assert result["epoch_at"].year == 1997
    assert result["epoch_at"].month == 11
    assert result["epoch_at"].day == 16
    assert result["epoch_at"].hour == 21
    assert result["epoch_at"].minute == 49
    assert result["epoch_at"].second == 37


def test_parse_tle_reports_checksum_values():
    result = parse_tle(NOAA_14_TLE)

    assert result["checksum"] == {"line1": 1, "line2": 5}
    assert result["computed_checksum"] == {"line1": 1, "line2": 5}
    assert result["checksum_valid"] is True
    assert calculate_tle_checksum(result["line1"]) == 1
    assert calculate_tle_checksum(result["line2"]) == 5


def test_parse_tle_accepts_two_line_input_without_name():
    result = parse_tle(ISS_TLE_WITHOUT_NAME)

    assert result["name"] is None
    assert result["catalog_number"] == "25544"
    assert result["international_designator"] == "1998-067A"
    assert result["epoch_full_year"] == 2026
    assert result["epoch_at"].year == 2026
    assert result["epoch_at"].month == 2
    assert result["epoch_at"].day == 28
    assert result["epoch_at"].hour == 12


def test_parse_tle_keeps_compatibility_aliases_and_derived_orbit_values():
    result = parse_tle(NOAA_14_TLE)

    assert result["inclination"] == result["inclination_deg"]
    assert result["raan"] == result["raan_deg"]
    assert result["arg_perigee"] == result["argument_of_perigee_deg"]
    assert result["mean_anomaly"] == result["mean_anomaly_deg"]
    assert result["mean_motion"] == result["mean_motion_rev_per_day"]
    assert result["orbital_period_minutes"] == pytest.approx(102.0038, rel=1e-4)
    assert result["semi_major_axis_km"] > 0
    assert result["apogee_km"] > result["perigee_km"]


def test_calculate_tle_orbit_elements_from_decoded_tle():
    decoded_tle = parse_tle(NOAA_14_TLE)

    orbit = calculate_tle_orbit_elements(decoded_tle)

    assert orbit == {
        "inclination_deg": pytest.approx(99.0090),
        "perigee_km": pytest.approx(decoded_tle["perigee_km"]),
        "apogee_km": pytest.approx(decoded_tle["apogee_km"]),
        "eccentricity": pytest.approx(0.0008546),
    }


def test_calculate_tle_orbit_elements_accepts_legacy_field_names():
    orbit = calculate_tle_orbit_elements(
        {
            "inclination": "86.5040",
            "eccentricity": "0.0001837",
            "mean_motion": "13.24413432",
        }
    )

    assert orbit["inclination_deg"] == pytest.approx(86.5040)
    assert orbit["eccentricity"] == pytest.approx(0.0001837)
    assert orbit["perigee_km"] > 0
    assert orbit["apogee_km"] > orbit["perigee_km"]


def test_calculate_tle_orbit_elements_requires_needed_fields():
    with pytest.raises(TleParseError, match="mean_motion"):
        calculate_tle_orbit_elements(
            {
                "inclination_deg": 86.5,
                "eccentricity": 0.0002,
            }
        )


def test_calculate_tle_orbit_elements_rejects_invalid_mean_motion():
    with pytest.raises(TleParseError, match="平均运动"):
        calculate_tle_orbit_elements(
            {
                "inclination_deg": 86.5,
                "eccentricity": 0.0002,
                "mean_motion_rev_per_day": 0,
            }
        )


def test_parse_tle_can_raise_on_bad_checksum():
    bad_checksum = NOAA_14_TLE.replace("2621", "2622")

    result = parse_tle(bad_checksum)
    assert result["line1_checksum_valid"] is False
    assert result["checksum_valid"] is False

    with pytest.raises(TleParseError, match="校验和"):
        parse_tle(bad_checksum, strict_checksum=True)


def test_parse_tle_rejects_multiple_records():
    with pytest.raises(TleParseError, match="单组"):
        parse_tle(NOAA_14_TLE + "\n" + ISS_TLE_WITHOUT_NAME)


def test_parse_tle_rejects_mismatched_catalog_numbers():
    bad_tle = NOAA_14_TLE.replace("2 23455", "2 99999")

    with pytest.raises(TleParseError, match="NORAD 编号"):
        parse_tle(bad_tle)


def test_parse_tle_rejects_short_lines():
    with pytest.raises(TleParseError, match="69"):
        parse_tle("1 23455U\n2 23455")
