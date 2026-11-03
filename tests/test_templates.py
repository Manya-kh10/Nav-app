import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.nav_state import NavStatus
from app.schemas.route import LatLon, Route, Step
from app.services.navigation.answers import answer, fmt_dist_kn, next_kannada
from app.services.navigation.sessions import Session


def _mock_session():
    step0 = Step(maneuver="depart", modifier=None, road="100 Feet Rd", distance_m=100, duration_s=60, lat=12.97, lon=77.64)
    step1 = Step(maneuver="turn", modifier="left", road="CMH Road", distance_m=200, duration_s=120, lat=12.975, lon=77.64)
    step2 = Step(maneuver="arrive", modifier=None, road="", distance_m=0, duration_s=0, lat=12.98, lon=77.64)
    route = Route(
        mode="walk",
        geometry=[[12.97, 77.64], [12.975, 77.64], [12.98, 77.64]],
        distance_m=300,
        duration_s=180,
        steps=[step0, step1, step2],
    )
    s = Session(
        route=route,
        instructions=[],
        landmarks={1: {"name": "Pai Electronics", "type": "shop"}},
        destination=LatLon(lat=12.98, lon=77.64),
        mode="walk",
    )
    s.last_status = NavStatus(
        on_route=True,
        needs_reroute=False,
        gps_quality="ok",
        distance_from_route_m=0.0,
        remaining_m=200.0,
        remaining_s=120.0,
        arrived=False,
        next_index=1,
        next_text="Turn left on CMH Road",
        distance_to_next_m=80.0,
    )
    s.last_status_at = time.time()
    return s


def test_fmt_dist_kn():
    assert fmt_dist_kn(100) == "100 ಮೀಟರ್"
    assert fmt_dist_kn(1500) == "1.5 ಕಿಲೋಮೀಟರ್"


def test_next_kannada():
    step = Step(maneuver="turn", modifier="left", road="CMH Road", distance_m=200, duration_s=120, lat=12.975, lon=77.64)
    text = next_kannada(step, 80, "Pai Electronics")
    assert "80 ಮೀಟರ್ ನಂತರ" in text
    assert "CMH Road ನಲ್ಲಿ" in text
    assert "ಎಡಕ್ಕೆ ತಿರುಗಿ" in text
    assert "Pai Electronics ಹತ್ತಿರ" in text


def test_kannada_answers():
    s = _mock_session()

    # Next turn
    res = answer(s, "ಮುಂದೆ ಎಲ್ಲಿ ತಿರುಗಬೇಕು?")
    assert res.lang == "kn"
    assert res.intent == "next_turn"
    assert "ಎಡಕ್ಕೆ ತಿರುಗಿ" in res.text

    # On route
    res = answer(s, "ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೇನಾ?")
    assert res.lang == "kn"
    assert res.intent == "on_route"
    assert "ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೀರಿ" in res.text

    # Time left
    res = answer(s, "ಎಷ್ಟು ಸಮಯ ಬೇಕು?")
    assert res.lang == "kn"
    assert res.intent == "time_left"
    assert "ನಿಮಿಷ ಬಾಕಿ ಇದೆ" in res.text

    # Distance left
    res = answer(s, "ಇನ್ನು ಎಷ್ಟು ದೂರ?")
    assert res.lang == "kn"
    assert res.intent == "distance_left"
    assert "ಮೀಟರ್ ಹೋಗಬೇಕು" in res.text

    # Kanglish question
    res = answer(s, "munde elli tirugabeku")
    assert res.lang == "kn"
    assert res.intent == "next_turn"
    assert "ಎಡಕ್ಕೆ ತಿರುಗಿ" in res.text
