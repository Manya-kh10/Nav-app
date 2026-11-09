import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.route import Step
from app.services.navigation.announcer import (
    AnnouncerConfig,
    AnnouncementState,
    build_driver_instruction,
    check_announcement,
    decide,
    format_spoken_dist,
    render_guidance,
    round_spoken_distance,
)


def _step(maneuver="turn", modifier="left", road="CMH Road", distance_m=200):
    return Step(
        maneuver=maneuver,
        modifier=modifier,
        road=road,
        distance_m=distance_m,
        duration_s=60,
        lat=12.97,
        lon=77.64,
    )


def test_distance_rounding():
    # < 200 m: nearest 10 m
    assert round_spoken_distance(48) == (50.0, "m")
    assert round_spoken_distance(120) == (120.0, "m")
    assert round_spoken_distance(15) == (20.0, "m")
    assert round_spoken_distance(5) == (10.0, "m")

    # 200 - 999 m: nearest 50 m
    assert round_spoken_distance(220) == (200.0, "m")
    assert round_spoken_distance(280) == (300.0, "m")
    assert round_spoken_distance(410) == (400.0, "m")
    assert round_spoken_distance(750) == (750.0, "m")
    assert round_spoken_distance(950) == (950.0, "m")
    assert round_spoken_distance(980) == (1.0, "km")

    # >= 1 km: nearest 0.1 km
    assert round_spoken_distance(1000) == (1.0, "km")
    assert round_spoken_distance(1400) == (1.4, "km")
    assert round_spoken_distance(1520) == (1.5, "km")
    assert round_spoken_distance(2100) == (2.1, "km")


def test_format_spoken_dist():
    assert format_spoken_dist(50, "m", "en") == "50 meters"
    assert format_spoken_dist(50, "m", "hi") == "50 मीटर"
    assert format_spoken_dist(50, "m", "hinglish") == "50 meter"
    assert format_spoken_dist(50, "m", "kn") == "50 ಮೀಟರ್"

    assert format_spoken_dist(1.5, "km", "en") == "1.5 kilometers"
    assert format_spoken_dist(1.5, "km", "hi") == "1.5 किलोमीटर"
    assert format_spoken_dist(1.5, "km", "hinglish") == "1.5 kilometer"
    assert format_spoken_dist(1.5, "km", "kn") == "1.5 ಕಿಲೋಮೀಟರ್"

    assert format_spoken_dist(1.0, "km", "en") == "1 kilometer"
    assert format_spoken_dist(1.0, "km", "hi") == "1 किलोमीटर"
    assert format_spoken_dist(1.0, "km", "hinglish") == "1 kilometer"
    assert format_spoken_dist(1.0, "km", "kn") == "1 ಕಿಲೋಮೀಟರ್"


def test_stage_order():
    """Stage order: ahead -> near -> chime (at now)."""
    state = AnnouncementState()
    step = _step(maneuver="turn", modifier="left", distance_m=500)

    # 1. AHEAD: at 500m (walk near_m is 50m, 500 > 75m)
    a1 = check_announcement(distance_to_next_m=500, step_index=1, step=step, on_route=True, arrived=False, state=state, landmark_name="Halasuru Police Station")
    assert a1 is not None
    assert a1.stage == "ahead"
    assert a1.speak is True
    assert a1.chime is False
    assert "In 500 meters, turn left near Halasuru Police Station." == a1.text

    # 2. NEAR: at 45m (<= 50m)
    a2 = check_announcement(distance_to_next_m=45, step_index=1, step=step, on_route=True, arrived=False, state=state, landmark_name="Halasuru Police Station")
    assert a2 is not None
    assert a2.stage == "near"
    assert a2.speak is True
    assert a2.chime is False
    assert "In 50 meters, turn left." == a2.text  # No landmark at near stage!

    # 3. NOW: at 10m (<= 15m) -> chime only, no speech
    a3 = check_announcement(distance_to_next_m=10, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a3 is not None
    assert a3.stage == "chime"
    assert a3.speak is False
    assert a3.chime is True
    assert a3.text == ""


def test_one_announcement_per_stage():
    """No repeated announcements within the same stage."""
    state = AnnouncementState()
    step = _step(maneuver="turn", modifier="left", distance_m=600)

    # First sighting in ahead
    a1 = check_announcement(distance_to_next_m=600, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a1 is not None
    assert a1.stage == "ahead"

    # Still in ahead (400m, 200m, 100m) -> no new announcement
    assert check_announcement(distance_to_next_m=400, step_index=1, step=step, on_route=True, arrived=False, state=state) is None
    assert check_announcement(distance_to_next_m=200, step_index=1, step=step, on_route=True, arrived=False, state=state) is None
    assert check_announcement(distance_to_next_m=100, step_index=1, step=step, on_route=True, arrived=False, state=state) is None

    # Enters near
    a2 = check_announcement(distance_to_next_m=45, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a2 is not None
    assert a2.stage == "near"

    # Still in near (35m, 25m, 18m) -> no new announcement
    assert check_announcement(distance_to_next_m=35, step_index=1, step=step, on_route=True, arrived=False, state=state) is None
    assert check_announcement(distance_to_next_m=20, step_index=1, step=step, on_route=True, arrived=False, state=state) is None

    # Enters now (chime)
    a3 = check_announcement(distance_to_next_m=12, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a3 is not None
    assert a3.stage == "chime"

    # Still at turn (8m, 4m) -> no new announcement
    assert check_announcement(distance_to_next_m=8, step_index=1, step=step, on_route=True, arrived=False, state=state) is None


def test_chime_on_flip_when_skipped():
    """If chime was skipped (fast sim, GPS jitter jumps from near directly to next step), play chime on flip."""
    state = AnnouncementState()
    step1 = _step(maneuver="turn", modifier="left", distance_m=100)
    step2 = _step(maneuver="turn", modifier="right", distance_m=300)

    # Step 1: enters near at 40m
    a1 = check_announcement(distance_to_next_m=40, step_index=1, step=step1, on_route=True, arrived=False, state=state)
    assert a1 is not None
    assert a1.stage == "near"

    # Fast jump: jumps directly from 40m to next step (step_index=2 at 250m) without ever hitting <= 15m
    a2 = check_announcement(distance_to_next_m=250, step_index=2, step=step2, on_route=True, arrived=False, state=state)
    assert a2 is not None
    assert a2.stage == "ahead"
    assert a2.chime is True  # Turn happened chime is triggered on flip!
    assert a2.speak is True
    assert "right" in a2.text


def test_next_ahead_after_turn():
    """After the turn is passed normally, the next step automatically gets its AHEAD announcement."""
    state = AnnouncementState()
    step1 = _step(maneuver="turn", modifier="left", distance_m=200)
    step2 = _step(maneuver="turn", modifier="right", distance_m=400)

    # Step 1 progression
    check_announcement(distance_to_next_m=200, step_index=1, step=step1, on_route=True, arrived=False, state=state)
    check_announcement(distance_to_next_m=40, step_index=1, step=step1, on_route=True, arrived=False, state=state)
    check_announcement(distance_to_next_m=10, step_index=1, step=step1, on_route=True, arrived=False, state=state)  # chime emitted

    # Turn completed: step flips to step 2 at 400m
    a_next = check_announcement(distance_to_next_m=400, step_index=2, step=step2, on_route=True, arrived=False, state=state)
    assert a_next is not None
    assert a_next.stage == "ahead"
    assert a_next.speak is True
    assert a_next.chime is False  # Chime was already emitted at 10m, so no double chime
    assert "In 400 meters, turn right." == a_next.text


def test_no_speech_at_now():
    """NOW stage emits chime only (speak=False, chime=True, text="")."""
    state = AnnouncementState()
    step = _step(maneuver="turn", modifier="left")
    check_announcement(distance_to_next_m=45, step_index=1, step=step, on_route=True, arrived=False, state=state)

    a_now = check_announcement(distance_to_next_m=12, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a_now is not None
    assert a_now.stage == "chime"
    assert a_now.speak is False
    assert a_now.chime is True
    assert a_now.text == ""


def test_none_while_off_route():
    """Silence while off-route (except the single reroute message)."""
    state = AnnouncementState()
    step = _step(maneuver="turn", modifier="left")

    # 1. Deviates off-route: single reroute announcement
    a_reroute = check_announcement(distance_to_next_m=50, step_index=1, step=step, on_route=False, arrived=False, state=state)
    assert a_reroute is not None
    assert a_reroute.stage == "reroute"
    assert a_reroute.priority == "high"

    # 2. Continues off-route: silence (no turn announcements, no duplicate reroute)
    assert check_announcement(distance_to_next_m=40, step_index=1, step=step, on_route=False, arrived=False, state=state) is None
    assert check_announcement(distance_to_next_m=20, step_index=1, step=step, on_route=False, arrived=False, state=state) is None
    assert check_announcement(distance_to_next_m=10, step_index=1, step=step, on_route=False, arrived=False, state=state) is None


def test_render_output_identical_for_announcement_and_live_text():
    """THE ONE RULE: render() output is identical for announcement and live text at same distance."""
    state = AnnouncementState()
    step = _step(maneuver="turn", modifier="left", road="Indiranagar 100 Feet Rd", distance_m=1500)
    lm = "Sony Center"

    # Emit AHEAD
    a = check_announcement(distance_to_next_m=1500, step_index=1, step=step, on_route=True, arrived=False, state=state, landmark_name=lm, lang="en")
    assert a is not None
    live = render_guidance(step, 1500, stage="ahead", lang="en", landmark=lm)
    assert a.text == live

    # Emit NEAR
    a_near = check_announcement(distance_to_next_m=50, step_index=1, step=step, on_route=True, arrived=False, state=state, landmark_name=lm, lang="en")
    assert a_near is not None
    live_near = render_guidance(step, 50, stage="near", lang="en", landmark=None)
    assert a_near.text == live_near

    # Test Hindi, Hinglish and Kannada match as well
    for lang in ["hi", "hinglish", "kn"]:
        st = AnnouncementState()
        ann = check_announcement(distance_to_next_m=1500, step_index=1, step=step, on_route=True, arrived=False, state=st, landmark_name=lm, lang=lang)
        assert ann is not None
        live_txt = render_guidance(step, 1500, stage="ahead", lang=lang, landmark=lm)
        assert ann.text == live_txt


def test_landmark_only_at_ahead():
    """Landmark is included only at AHEAD stage, never at near or now."""
    step = _step(maneuver="turn", modifier="left")
    lm = "Metro Station"

    # Ahead: includes landmark
    ahead_text = render_guidance(step, 800, "ahead", "en", landmark=lm)
    assert "Metro Station" in ahead_text

    # Near: ignores landmark
    near_text = render_guidance(step, 50, "near", "en", landmark=lm)
    assert "Metro Station" not in near_text

    # Now: ignores landmark
    now_text = render_guidance(step, 10, "now", "en", landmark=lm)
    assert "Metro Station" not in now_text


def test_skip_straight_steps():
    """Skip steps whose modifier is straight or maneuver is continue (config flag on by default)."""
    state = AnnouncementState()
    cfg = AnnouncerConfig(skip_straight_steps=True)
    step_straight = Step(maneuver="continue", modifier="straight", road="MG Road", distance_m=1000, duration_s=100, lat=12.97, lon=77.64)

    # Straight step emits no ahead or near
    a = check_announcement(distance_to_next_m=1000, step_index=1, step=step_straight, on_route=True, arrived=False, state=state, config=cfg)
    assert a is None
    a_near = check_announcement(distance_to_next_m=50, step_index=1, step=step_straight, on_route=True, arrived=False, state=state, config=cfg)
    assert a_near is None
