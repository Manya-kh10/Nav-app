import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.nav_state import NavStatus
from app.schemas.route import LatLon, Route, Step
from app.services.navigation.answers import answer
from app.services.navigation.sessions import Session
from app.services.traffic import budget
from app.services.traffic.adapter import adapt_tomtom_route, build_traffic_spoken_summary, compute_traffic_level
from app.services.traffic.incidents import check_incident_announcement, filter_incidents_on_route, get_route_bbox
from app.services.traffic.provider import TrafficIncident, TrafficLevel, TrafficSnapshot, TrafficSummary


def test_compute_traffic_level():
    # Delay < 2 min (120s) -> NONE
    assert compute_traffic_level(60, 1000) == TrafficLevel.NONE
    assert compute_traffic_level(0, 500) == TrafficLevel.NONE

    # Delay < 10% of free flow -> NONE
    assert compute_traffic_level(110, 1200) == TrafficLevel.NONE

    # Delay 2-7 min and 10-35% -> LIGHT
    assert compute_traffic_level(240, 1000) == TrafficLevel.LIGHT

    # Delay >= 7 min (420s) or >= 35% -> HEAVY
    assert compute_traffic_level(450, 1200) == TrafficLevel.HEAVY
    assert compute_traffic_level(400, 800) == TrafficLevel.HEAVY  # 50% delay


def test_adapt_tomtom_route():
    fixture = {
        "routes": [
            {
                "summary": {
                    "lengthInMeters": 1500,
                    "travelTimeInSeconds": 1200,
                    "trafficDelayInSeconds": 200,
                    "noTrafficTravelTimeInSeconds": 1000,
                },
                "legs": [
                    {
                        "points": [
                            {"latitude": 12.9716, "longitude": 77.5946},
                            {"latitude": 12.9750, "longitude": 77.5990},
                            {"latitude": 12.9800, "longitude": 77.6050},
                        ]
                    }
                ],
                "guidance": {
                    "instructions": [
                        {
                            "routeOffsetInMeters": 0,
                            "travelTimeInSeconds": 0,
                            "point": {"latitude": 12.9716, "longitude": 77.5946},
                            "maneuver": "DEPART",
                            "street": "MG Road",
                        },
                        {
                            "routeOffsetInMeters": 500,
                            "travelTimeInSeconds": 180,
                            "point": {"latitude": 12.9750, "longitude": 77.5990},
                            "maneuver": "TURN_LEFT",
                            "street": "Brigade Road",
                        },
                        {
                            "routeOffsetInMeters": 1500,
                            "travelTimeInSeconds": 600,
                            "point": {"latitude": 12.9800, "longitude": 77.6050},
                            "maneuver": "ARRIVE",
                            "street": "",
                        },
                    ]
                },
            }
        ]
    }

    route, summary = adapt_tomtom_route(fixture, fetched_at=time.time())
    assert route.distance_m == 1500.0
    assert route.duration_s == 1200.0
    assert len(route.steps) == 3
    assert route.steps[0].maneuver == "depart"
    assert route.steps[1].maneuver == "turn"
    assert route.steps[1].modifier == "left"
    assert route.steps[1].road == "Brigade Road"
    assert route.steps[1].distance_m == 1000.0
    assert route.steps[2].maneuver == "arrive"

    assert summary.delay_s == 200
    assert summary.level == TrafficLevel.LIGHT
    assert summary.provider == "tomtom"


def test_build_traffic_spoken_summary():
    # Light traffic
    s_light = TrafficSummary(travel_time_s=1200, no_traffic_travel_time_s=1000, delay_s=200, level=TrafficLevel.LIGHT, fetched_at=time.time())
    p_en = build_traffic_spoken_summary(s_light, "en")
    assert "20 minutes" in p_en
    assert "light" in p_en
    assert len(p_en.split()) <= 12

    # Heavy traffic
    s_heavy = TrafficSummary(travel_time_s=1920, no_traffic_travel_time_s=1200, delay_s=720, level=TrafficLevel.HEAVY, fetched_at=time.time())
    p_hi = build_traffic_spoken_summary(s_heavy, "hinglish")
    assert "heavy" in p_hi
    assert len(p_hi.split()) <= 12


def test_incident_filtering_distance_and_ahead():
    # Route along latitude 12.970 -> 12.980 (approx 1113 meters)
    geometry = [[12.970, 77.600], [12.975, 77.600], [12.980, 77.600]]

    incidents = [
        # 1. 20m off route, 600m along (ahead of user at 300m) -> KEEP
        TrafficIncident("1", "Accident", "Car crash", 12.9750, 77.6002, 300, 50),
        # 2. 150m off route (too far) -> EXCLUDE
        TrafficIncident("2", "Road Works", "Repair", 12.9750, 77.6015, 100, 20),
        # 3. 10m off route, but behind user (12.971 is at ~110m along, user is at 300m) -> EXCLUDE
        TrafficIncident("3", "Jam", "Slow", 12.9710, 77.6001, 200, 100),
    ]

    filtered = filter_incidents_on_route(incidents, geometry, user_along_m=300.0)
    assert len(filtered) == 1
    assert filtered[0].id == "1"
    assert filtered[0].category == "Accident"


def test_incident_announcement_rate_limiting():
    geometry = [[12.970, 77.600], [12.980, 77.600]]
    inc = TrafficIncident("inc-1", "Accident", "Crash", 12.978, 77.600, 300, 50)
    snapshot = TrafficSnapshot(incidents=[inc])

    now = 1000.0
    # User at 0m, incident at ~890m ahead (< 1500m)
    ann1 = check_incident_announcement(snapshot, user_along_m=0.0, geometry=geometry, now=now)
    assert ann1 is not None
    assert "Accident" in ann1.text
    assert "Traffic alert" in ann1.text

    # Next tick 30s later: rate-limited (gap < 120s)
    ann2 = check_incident_announcement(snapshot, user_along_m=50.0, geometry=geometry, now=now + 30.0)
    assert ann2 is None


def test_budget_enforcement():
    budget.reset_for_test(calls=399)
    assert budget.can_call() is True

    budget.record_call("test_call")
    # Now at 400 (cap reached)
    assert budget.can_call() is False

    usage = budget.get_usage()
    assert usage["calls_today"] == 400
    assert usage["cap_reached"] is True

    # Reset back for clean state
    budget.reset_for_test(calls=0)


def _mock_traffic_session(ts_age_s: float = 0.0):
    route = Route(
        mode="drive",
        geometry=[[12.97, 77.64], [12.975, 77.64], [12.98, 77.64]],
        distance_m=1000,
        duration_s=600,
        steps=[
            Step(maneuver="depart", modifier=None, road="100 Feet Rd", distance_m=500, duration_s=300, lat=12.97, lon=77.64),
            Step(maneuver="arrive", modifier=None, road="", distance_m=0, duration_s=0, lat=12.98, lon=77.64),
        ],
    )
    s = Session(
        route=route,
        instructions=[],
        landmarks={},
        destination=LatLon(lat=12.98, lon=77.64),
        mode="drive",
    )
    s.last_status = NavStatus(
        on_route=True,
        needs_reroute=False,
        gps_quality="ok",
        distance_from_route_m=0.0,
        remaining_m=500.0,
        remaining_s=300.0,
        arrived=False,
        next_index=0,
        next_text="Continue on 100 Feet Rd",
        distance_to_next_m=200.0,
    )
    s.last_status_at = time.time()
    if ts_age_s >= 0:
        s.traffic_snapshot = TrafficSnapshot(
            summary=TrafficSummary(
                travel_time_s=600,
                no_traffic_travel_time_s=480,
                delay_s=120,
                level=TrafficLevel.LIGHT,
                fetched_at=time.time() - ts_age_s,
            )
        )
    return s


def test_traffic_query_answers_fresh_stale_and_unavailable():
    # 1. Fresh traffic query
    s_fresh = _mock_traffic_session(ts_age_s=60.0)
    res_traffic = answer(s_fresh, "how is the traffic ahead?")
    assert res_traffic.intent == "traffic_ahead"
    assert "Traffic is light" in res_traffic.text
    assert "checked 1 minutes ago" in res_traffic.text or "checked just now" in res_traffic.text

    res_delay = answer(s_fresh, "how much delay?")
    assert res_delay.intent == "delay"
    assert "2 minutes delay" in res_delay.text

    # 2. Outdated traffic query (> 10 minutes = 700s)
    s_stale = _mock_traffic_session(ts_age_s=700.0)
    res_stale = answer(s_stale, "how is the traffic?")
    assert "outdated" in res_stale.text.lower()

    # 3. Traffic unavailable (no snapshot)
    s_none = _mock_traffic_session(ts_age_s=-1.0)
    s_none.traffic_snapshot.summary = None
    res_none = answer(s_none, "how is the traffic?")
    assert "not available" in res_none.text.lower()


@patch("app.api.v1.navigation.traffic_provider.get_route_with_traffic")
@patch("app.api.v1.navigation.traffic_provider.get_incidents_in_bbox")
def test_navigation_guide_tomtom_and_fallback(mock_incs, mock_traffic):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. TomTom Succeeds
    mock_traffic.return_value = (
        Route(
            mode="drive",
            geometry=[[12.9716, 77.5946], [12.9800, 77.6050]],
            distance_m=1200,
            duration_s=600,
            steps=[
                Step(maneuver="depart", modifier=None, road="MG Road", distance_m=1200, duration_s=600, lat=12.9716, lon=77.5946),
                Step(maneuver="arrive", modifier=None, road="", distance_m=0, duration_s=0, lat=12.98, lon=77.605),
            ],
        ),
        TrafficSummary(
            travel_time_s=600,
            no_traffic_travel_time_s=480,
            delay_s=120,
            level=TrafficLevel.LIGHT,
            fetched_at=time.time(),
        ),
    )
    mock_incs.return_value = []

    res = client.post(
        "/api/v1/navigation/guide",
        json={
            "start": {"lat": 12.9716, "lon": 77.5946},
            "end": {"lat": 12.9800, "lon": 77.6050},
            "mode": "drive",
            "landmarks": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["traffic_status"] == "available"
    assert data["route"]["traffic"] is not None
    assert data["route"]["traffic"]["level"] == "light"
    assert "Traffic is light" in data["route"]["traffic"]["spoken_summary"]
    assert "TomTom" in data["route"]["traffic"]["attribution"]

    # 2. TomTom Fails -> Graceful fallback to OSRM
    mock_traffic.return_value = None
    res_fallback = client.post(
        "/api/v1/navigation/guide",
        json={
            "start": {"lat": 12.9716, "lon": 77.5946},
            "end": {"lat": 12.9800, "lon": 77.6050},
            "mode": "drive",
            "landmarks": False,
        },
    )
    assert res_fallback.status_code == 200
    data_fallback = res_fallback.json()
    assert data_fallback["traffic_status"] in ("unavailable", "budget_exceeded")
    assert "not include traffic" in data_fallback["route"]["eta_note"]

    # 3. GET /api/v1/traffic/usage
    res_usage = client.get("/api/v1/traffic/usage")
    assert res_usage.status_code == 200
    usage_data = res_usage.json()
    assert "calls_today" in usage_data
    assert "daily_cap" in usage_data
    assert "remaining" in usage_data

