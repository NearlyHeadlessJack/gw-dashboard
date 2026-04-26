from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from gw.config import AppConfig, BackendConfig, DatabaseConfig, FrontendConfig
from gw.database import DatabaseManager
from gw.web.app import create_app


RAW_TLE_A = """\
HULIANWANG DIGUI-01
1 62323U 24240A   26115.49220466  .00000041  00000+0  60880-4 0  9996
2 62323  86.5040   1.0150 0001837  72.4834 287.6500 13.24413432 65663
"""

RAW_TLE_B = """\
HULIANWANG DIGUI-02
1 62324U 24240B   26115.49966838  .00000039  00000+0  57141-4 0  9990
2 62324  86.5069   1.1568 0001856  73.6881 286.4457 13.24412762 65679
"""

RAW_GEO_TLE = """\
GEO TEST
1 41866U 16071A   26115.50000000 -.00000127  00000+0  00000+0 0  9990
2 41866   0.0170  85.1900 0001940  85.4000 112.2000  1.00270000 34458
"""

RAW_SSO_TLE = """\
SSO TEST
1 62323U 24240A   26115.49220466  .00000041  00000+0  60880-4 0  9996
2 62323  97.5000   1.0150 0001837  72.4834 287.6500 14.24413432 65663
"""


@pytest.fixture
def client():
    db = DatabaseManager("sqlite3", ":memory:")
    db.initialize_database()
    manufacturer_id = db.create_manufacturer("五院", group_count=1, satellite_count=2)
    rocket_id = db.create_rocket(
        "长征六号改",
        serial_number="Y1",
        launch_count=1,
        satellite_count=2,
    )
    group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2024-240",
        launch_time=datetime(2024, 12, 16, 10, 0),
        launch_site="太原",
        rocket_id=rocket_id,
        manufacturer_id=manufacturer_id,
        satellite_count=2,
        valid_satellite_count=1,
        invalid_satellite_count=1,
        raw_tle=RAW_TLE_A,
    )
    db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 0),
        intl_designator="2024-240A",
        raw_tle=RAW_TLE_A,
    )
    db.add_group_satellite(
        group_id,
        epoch_at=datetime(2026, 4, 26, 8, 5),
        intl_designator="2024-240B",
        status="失效",
        raw_tle=RAW_TLE_B,
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 7, 30),
        raw_tle=RAW_TLE_A,
    )
    db.add_satellite_record(
        "2024-240A",
        epoch_at=datetime(2026, 4, 26, 8, 0),
        raw_tle=RAW_TLE_B,
    )
    db.set_metainfo(
        datetime(2026, 4, 26, 8, 10, tzinfo=timezone.utc),
        valid_duration_seconds=3600,
        satellite_record_limit=100,
    )

    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir="/tmp/gw-dashboard-missing-dist"),
    )
    app = create_app(config, database=db, start_daemon=False)
    return TestClient(app)


def test_dashboard_api_returns_overview(client):
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_satellites"] == 2
    assert payload["summary"]["valid_satellites"] == 1
    assert payload["summary"]["invalid_satellites"] == 1
    assert payload["summary"]["tracked_satellites"] == 2
    assert payload["recent_satellites"][0]["group_name"] == "低轨01组"
    assert payload["recent_launches"][0]["rocket_name"] == "长征六号改"
    assert payload["recent_launches"][0]["manufacturer_name"] == "五院"
    assert payload["manufacturers"][0]["name"] == "五院"
    assert payload["rockets"][0]["name"] == "长征六号改"
    assert payload["rockets"][0]["serial_number"] is None


def test_launches_api_returns_all_launches_newest_first():
    db = DatabaseManager("sqlite3", ":memory:")
    db.initialize_database()
    manufacturer_id = db.create_manufacturer("五院", group_count=9, satellite_count=45)
    for index in range(9):
        db.create_satellite_group(
            name=f"低轨{index + 1:02d}组",
            intl_designator=f"2026-{index + 1:03d}",
            launch_time=datetime(2026, 1, index + 1, 10, 0),
            manufacturer_id=manufacturer_id,
            satellite_count=index + 1,
        )
    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir="/tmp/gw-dashboard-missing-dist"),
    )
    launches_client = TestClient(create_app(config, database=db, start_daemon=False))

    launches_response = launches_client.get("/api/launches")
    dashboard_response = launches_client.get("/api/dashboard")

    assert launches_response.status_code == 200
    launches = launches_response.json()
    assert len(launches) == 9
    assert launches[0]["intl_designator"] == "2026-009"
    assert launches[0]["manufacturer_name"] == "五院"
    assert launches[-1]["intl_designator"] == "2026-001"
    assert len(dashboard_response.json()["recent_launches"]) == 8


def test_satellites_api_returns_all_current_satellites_newest_first():
    db = DatabaseManager("sqlite3", ":memory:")
    db.initialize_database()
    group_id = db.create_satellite_group(
        name="低轨01组",
        intl_designator="2026-001",
        launch_time=datetime(2026, 1, 1, 10, 0),
        satellite_count=11,
        valid_satellite_count=11,
    )
    for index, piece in enumerate("ABCDEFGHIJK"):
        db.add_group_satellite(
            group_id,
            epoch_at=datetime(2026, 1, 1, 11, index),
            intl_designator=f"2026-001{piece}",
        )
    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir="/tmp/gw-dashboard-missing-dist"),
    )
    satellites_client = TestClient(create_app(config, database=db, start_daemon=False))

    satellites_response = satellites_client.get("/api/satellites")
    dashboard_response = satellites_client.get("/api/dashboard")

    assert satellites_response.status_code == 200
    satellites = satellites_response.json()
    assert len(satellites) == 11
    assert satellites[0]["intl_designator"] == "2026-001K"
    assert satellites[-1]["intl_designator"] == "2026-001A"
    assert len(dashboard_response.json()["recent_satellites"]) == 10


def test_dashboard_api_aggregates_rocket_statistics_by_model():
    db = DatabaseManager("sqlite3", ":memory:")
    db.initialize_database()
    db.create_rocket(
        "长征十二号",
        serial_number="Y1",
        launch_count=1,
        satellite_count=10,
    )
    db.create_rocket(
        "长征十二号",
        serial_number="Y2",
        launch_count=2,
        satellite_count=20,
    )
    db.create_rocket(
        "长征五号B",
        serial_number="Y3",
        launch_count=1,
        satellite_count=8,
    )
    db.create_rocket(
        "长征五号B/远征二号",
        launch_count=1,
        satellite_count=4,
    )
    db.create_rocket(
        "长征五号B Y4/远征二号",
        launch_count=1,
        satellite_count=6,
    )
    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir="/tmp/gw-dashboard-missing-dist"),
    )
    stats_client = TestClient(create_app(config, database=db, start_daemon=False))

    response = stats_client.get("/api/dashboard")

    assert response.status_code == 200
    rockets = {rocket["name"]: rocket for rocket in response.json()["rockets"]}
    assert list(rockets) == ["长征十二号", "长征五号B"]
    assert rockets["长征十二号"]["serial_number"] is None
    assert rockets["长征十二号"]["launch_count"] == 3
    assert rockets["长征十二号"]["satellite_count"] == 30
    assert rockets["长征五号B"]["serial_number"] is None
    assert rockets["长征五号B"]["launch_count"] == 3
    assert rockets["长征五号B"]["satellite_count"] == 18


def test_group_and_satellite_detail_api(client):
    group_response = client.get("/api/groups/2024-240")
    satellite_response = client.get("/api/satellites/2024-240A")

    assert group_response.status_code == 200
    assert group_response.json()["satellites"][0]["intl_designator"] == "2024-240A"
    assert satellite_response.status_code == 200
    satellite = satellite_response.json()
    assert satellite["intl_designator"] == "2024-240A"
    assert satellite["orbit"]["perigee_km"] is not None


def test_satellite_history_api_returns_chart_points_oldest_first(client):
    response = client.get("/api/satellites/2024-240A/history")

    assert response.status_code == 200
    payload = response.json()
    assert [point["epoch_at"] for point in payload] == [
        "2026-04-26T07:30:00",
        "2026-04-26T08:00:00",
    ]
    assert payload[0]["perigee_km"] is not None
    assert payload[0]["apogee_km"] is not None


def test_map_groups_api_returns_group_positions_and_previous_orbit_tracks(client):
    response = client.get("/api/map/groups?at=2026-04-26T08:00:00Z")

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_at"] == "2026-04-26T08:00:00Z"
    assert len(payload["groups"]) == 1
    first = payload["groups"][0]
    assert first["name"] == "低轨01组"
    assert first["intl_designator"] == "2024-240"
    assert first["representative_intl_designator"] == "2024-240A"
    assert first["satellite_count"] == 2
    assert first["orbit_type"] == "leo"
    assert -90 <= first["position"]["latitude"] <= 90
    assert -180 <= first["position"]["longitude"] <= 180
    assert len(first["track"]) == 601
    assert first["track"][-1]["timestamp"] == "2026-04-26T08:00:00Z"


def test_map_points_api_returns_satellite_positions_without_tracks(client):
    response = client.get("/api/map/points?at=2026-04-26T08:00:00Z")

    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_at"] == "2026-04-26T08:00:00Z"
    assert len(payload["satellites"]) == 2
    first = payload["satellites"][0]
    assert first["intl_designator"] == "2024-240A"
    assert first["group_name"] == "低轨01组"
    assert "track" not in first
    assert -90 <= first["position"]["latitude"] <= 90
    assert -180 <= first["position"]["longitude"] <= 180


def test_map_groups_api_marks_geo_groups():
    db = DatabaseManager("sqlite3", ":memory:")
    db.initialize_database()
    db.create_satellite_group(
        name="高轨01星",
        intl_designator="2024-001",
        satellite_count=1,
        valid_satellite_count=1,
        raw_tle=RAW_GEO_TLE,
    )
    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir="/tmp/gw-dashboard-missing-dist"),
    )
    geo_client = TestClient(create_app(config, database=db, start_daemon=False))

    response = geo_client.get("/api/map/groups?at=2026-04-26T08:00:00Z")

    assert response.status_code == 200
    group = response.json()["groups"][0]
    assert group["orbit_type"] == "geo"
    assert group["orbit"]["perigee_km"] > 35000
    assert group["position"]["altitude_km"] > 35000


def test_map_groups_api_marks_sso_groups():
    db = DatabaseManager("sqlite3", ":memory:")
    db.initialize_database()
    db.create_satellite_group(
        name="太阳同步01组",
        intl_designator="2024-002",
        satellite_count=1,
        valid_satellite_count=1,
        raw_tle=RAW_SSO_TLE,
    )
    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir="/tmp/gw-dashboard-missing-dist"),
    )
    sso_client = TestClient(create_app(config, database=db, start_daemon=False))

    response = sso_client.get("/api/map/groups?at=2026-04-26T08:00:00Z")

    assert response.status_code == 200
    group = response.json()["groups"][0]
    assert group["orbit_type"] == "sso"
    assert 95 <= group["orbit"]["inclination_deg"] <= 105
    assert 300 <= group["orbit"]["perigee_km"] <= 2000
    assert group["orbit"]["apogee_km"] <= 2000


def test_map_satellites_api_rejects_invalid_time(client):
    response = client.get("/api/map/satellites?at=not-a-time")

    assert response.status_code == 400


def test_backend_serves_frontend_dist_as_single_process_app(tmp_path):
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<main>GW Dashboard</main>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('gw')", encoding="utf-8")

    db = DatabaseManager("sqlite3", ":memory:")
    config = AppConfig(
        database=DatabaseConfig(type="sqlite3", connection=":memory:"),
        backend=BackendConfig(cache_ttl_seconds=0),
        frontend=FrontendConfig(dist_dir=str(dist_dir)),
    )
    frontend_client = TestClient(create_app(config, database=db, start_daemon=False))

    assert frontend_client.get("/").text == "<main>GW Dashboard</main>"
    assert frontend_client.get("/dashboard/history").text == "<main>GW Dashboard</main>"
    assert frontend_client.get("/map").text == "<main>GW Dashboard</main>"
    assert frontend_client.get("/assets/app.js").text == "console.log('gw')"
    assert frontend_client.get("/api/not-found").status_code == 404
