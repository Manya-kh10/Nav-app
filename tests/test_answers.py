import pytest
from app.schemas.nav_state import NavStatus
from app.schemas.route import Instruction, LatLon, Route, Step
from app.services.navigation.answers import answer
from app.services.navigation.sessions import Session


def make_dummy_session(driver_lang="en", mode="walk"):
    step0 = Step(maneuver="depart", modifier="straight", distance_m=50.0, duration_s=40.0, lat=12.97, lon=77.59, road="MG Road")
    step1 = Step(maneuver="turn", modifier="left", distance_m=200.0, duration_s=150.0, lat=12.971, lon=77.591, road="Brigade Road")
    step2 = Step(maneuver="arrive", modifier="straight", distance_m=0.0, duration_s=0.0, lat=12.972, lon=77.592, road="")
    route = Route(
        mode=mode,
        geometry=[[12.97, 77.59], [12.971, 77.591], [12.972, 77.592]],
        distance_m=250.0,
        duration_s=190.0,
        steps=[step0, step1, step2],
        eta_note="Pedestrian walk mode",
    )
    instructions = [
        Instruction(text="Start walking on MG Road.", maneuver="depart", modifier="straight", distance_to_m=0.0, lat=12.97, lon=77.59),
        Instruction(text="Turn left onto Brigade Road.", maneuver="turn", modifier="left", distance_to_m=50.0, lat=12.971, lon=77.591),
        Instruction(text="You will arrive at your destination.", maneuver="arrive", modifier="straight", distance_to_m=200.0, lat=12.972, lon=77.592),
    ]
    s = Session(
        route=route,
        instructions=instructions,
        landmarks={1: {"name": "Halasuru Police Station", "kind": "police"}},
        destination=LatLon(lat=12.972, lon=77.592),
        mode=mode,
        driver_lang=driver_lang,
    )
    # Set fresh nav status
    s.last_status = NavStatus(
        on_route=True,
        needs_reroute=False,
        gps_quality="ok",
        distance_from_route_m=0.0,
        remaining_m=250.0,
        remaining_s=190.0,
        arrived=False,
        next_index=1,
        next_text="Turn left onto Brigade Road",
        distance_to_next_m=50.0,
        speed_mps=1.3,
    )
    s.last_status_at = 9999999999.0  # perpetually fresh
    return s


def test_answer_hindi_devanagari():
    s = make_dummy_session()

    # Time left
    res = answer(s, "और कितना चलना है मुझे?")
    assert res.intent == "time_left"
    assert res.lang == "hi"
    assert "मिनट" in res.text
    assert "चलना बाकी है" in res.text
    assert "traffic" not in res.text.lower()

    # Next turn
    res = answer(s, "अब मैं कहाँ जाऊँ?")
    assert res.intent == "next_turn"
    assert res.lang == "hi"
    assert "बाएँ" in res.text or "मुड़ें" in res.text

    # On route
    res = answer(s, "क्या यह मोड़ सही है?")
    assert res.intent == "on_route"
    assert res.lang == "hi"
    assert "हाँ, आप सही रास्ते पर हैं" in res.text


def test_answer_hinglish():
    s = make_dummy_session()

    # Time left in Hinglish
    res = answer(s, "और कितना time लगेगा?")
    assert res.intent == "time_left"
    assert res.lang == "hinglish"
    assert "Lagbhag" in res.text
    assert "minute" in res.text

    # Next turn in Hinglish
    res = answer(s, "ab mujhe kahan mudna hai?")
    assert res.intent == "next_turn"
    assert res.lang == "hinglish"
    assert "left" in res.text

    # On route in Hinglish
    res = answer(s, "kya yeh turn sahi hai?")
    assert res.intent == "on_route"
    assert res.lang == "hinglish"
    assert "sahi raste par hain" in res.text


def test_answer_english():
    s = make_dummy_session()

    # Next turn
    res = answer(s, "Where should I go next?")
    assert res.intent == "next_turn"
    assert res.lang == "en"
    assert "left" in res.text.lower()

    # On route
    res = answer(s, "Is this the right turn?")
    assert res.intent == "on_route"
    assert res.lang == "en"
    assert "right route" in res.text.lower()

    # Time left
    res = answer(s, "How long do I have to walk?")
    assert res.intent == "time_left"
    assert res.lang == "en"
    assert "minutes left" in res.text.lower()
    assert "traffic" not in res.text.lower()


def test_answer_user_lang_override():
    s = make_dummy_session()

    # English query, but user selected Hindi
    res = answer(s, "Where should I go next?", user_lang="hi")
    assert res.intent == "next_turn"
    assert res.lang == "hi"
    assert "मुड़ें" in res.text or "बाएँ" in res.text

    # English query, but user selected Hinglish
    res = answer(s, "Is this the right turn?", user_lang="hinglish")
    assert res.intent == "on_route"
    assert res.lang == "hinglish"
    assert "sahi raste par hain" in res.text
