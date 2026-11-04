import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.route import Step
from app.services.navigation.announcer import (
    AnnouncerConfig,
    AnnouncementState,
    build_driver_instruction,
    check_announcement,
    format_spoken_dist,
    round_spoken_distance,
)


def _step(maneuver="turn", modifier="left", road="100 Feet Rd", distance_m=200):
    return Step(
        maneuver=maneuver,
        modifier=modifier,
        road=road,
        distance_m=distance_m,
        duration_s=60,
        lat=12.97,
        lon=77.64,
    )


def test_round_spoken_distance():
    # Buckets: 50, 100, 150, 200, 300, 400, 500, 600, 800
    assert round_spoken_distance(48) == (50.0, "m")
    assert round_spoken_distance(120) == (100.0, "m")
    assert round_spoken_distance(145) == (150.0, "m")
    assert round_spoken_distance(280) == (300.0, "m")
    assert round_spoken_distance(410) == (400.0, "m")
    assert round_spoken_distance(750) == (800.0, "m")
    assert round_spoken_distance(950) == (1.0, "km")
    assert round_spoken_distance(1400) == (1.5, "km")
    assert round_spoken_distance(2100) == (2.0, "km")


def test_format_spoken_dist_languages():
    assert format_spoken_dist(100, "m", "en") == "100 meters"
    assert format_spoken_dist(100, "m", "hinglish") == "100 meter"
    assert format_spoken_dist(100, "m", "kn") == "100 ಮೀಟರ್"

    assert format_spoken_dist(1.0, "km", "en") == "1 kilometer"
    assert format_spoken_dist(1.5, "km", "en") == "1.5 kilometers"
    assert format_spoken_dist(1.5, "km", "hinglish") == "1.5 kilometer"
    assert format_spoken_dist(1.5, "km", "kn") == "1.5 ಕಿಲೋಮೀಟರ್"


def test_driver_phrasing_rules_word_count_and_sentences():
    step = _step(maneuver="turn", modifier="left", road="CMH Road")

    # English phrases
    for stage in ["far", "near", "now"]:
        p = build_driver_instruction(stage=stage, step=step, distance_to_next_m=120, landmark_name="Pai Electronics", lang="en")
        words = p.split()
        assert len(words) <= 12, f"En {stage} exceeded 12 words: {p}"
        assert p.endswith(".")
        assert p.count(".") == 1

    # Hinglish phrases
    for stage in ["far", "near", "now"]:
        p = build_driver_instruction(stage=stage, step=step, distance_to_next_m=120, landmark_name="Pai Electronics", lang="hinglish")
        words = p.split()
        assert len(words) <= 12, f"Hi {stage} exceeded 12 words: {p}"
        assert p.endswith(".")
        assert p.count(".") == 1

    # Kannada phrases (UNVERIFIED flag enabled)
    cfg_kn = AnnouncerConfig(enable_kannada_driver=True)
    for stage in ["far", "near", "now"]:
        p = build_driver_instruction(stage=stage, step=step, distance_to_next_m=120, landmark_name="Pai Electronics", lang="kn", config=cfg_kn)
        words = p.split()
        assert len(words) <= 12, f"Kn {stage} exceeded 12 words: {p}"
        assert p.endswith(".")
        assert p.count(".") == 1


def test_landmark_only_at_near_stage():
    step = _step(maneuver="turn", modifier="left", road="CMH Road")
    lm = "Pai Electronics"

    # Far stage: landmark MUST NOT appear
    p_far = build_driver_instruction(stage="far", step=step, distance_to_next_m=400, landmark_name=lm, lang="en")
    assert "Pai Electronics" not in p_far

    # Near stage: landmark MUST appear
    p_near = build_driver_instruction(stage="near", step=step, distance_to_next_m=100, landmark_name=lm, lang="en")
    assert "Pai Electronics" in p_near

    # Now stage: landmark MUST NOT appear
    p_now = build_driver_instruction(stage="now", step=step, distance_to_next_m=20, landmark_name=lm, lang="en")
    assert "Pai Electronics" not in p_now


def test_road_omitted_if_more_than_three_words():
    step_long_road = _step(maneuver="turn", modifier="left", road="Swami Vivekananda Road Extension East")
    p = build_driver_instruction(stage="far", step=step_long_road, distance_to_next_m=400, lang="en")
    assert "Swami Vivekananda" not in p
    assert p == "In 400 meters, turn left."


def test_simulated_drive_at_8_mps():
    """8 m/s (~29 km/h):
    far <= max(400, 8*40=320) = 400m
    near <= max(120, 8*15=120) = 120m
    now <= 30m
    """
    state = AnnouncementState()
    step = _step()
    speed = 8.0

    # 500m: outside far threshold
    a1 = check_announcement(distance_to_next_m=500, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a1 is None

    # 380m: enters far
    a2 = check_announcement(distance_to_next_m=380, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a2 is not None
    assert a2.stage == "far"
    assert a2.priority == "normal"

    # 300m: still in far, should NOT repeat
    a3 = check_announcement(distance_to_next_m=300, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a3 is None

    # 100m: enters near
    a4 = check_announcement(distance_to_next_m=100, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state, landmark_name="Empire Hotel")
    assert a4 is not None
    assert a4.stage == "near"
    assert a4.priority == "normal"
    assert "Empire Hotel" in a4.text

    # 60m: still in near, should NOT repeat
    a5 = check_announcement(distance_to_next_m=60, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a5 is None

    # 25m: enters now
    a6 = check_announcement(distance_to_next_m=25, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a6 is not None
    assert a6.stage == "now"
    assert a6.priority == "high"
    assert "now" in a6.text.lower()

    # 10m: still in now, should NOT repeat
    a7 = check_announcement(distance_to_next_m=10, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a7 is None


def test_simulated_drive_at_15_mps_dynamic_thresholds():
    """15 m/s (~54 km/h):
    far <= max(400, 15*40=600) = 600m
    near <= max(120, 15*15=225) = 225m
    now <= 30m
    """
    state = AnnouncementState()
    step = _step()
    speed = 15.0

    # 550m: triggers far because 550 <= 600
    a1 = check_announcement(distance_to_next_m=550, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a1 is not None
    assert a1.stage == "far"

    # 200m: triggers near because 200 <= 225
    a2 = check_announcement(distance_to_next_m=200, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a2 is not None
    assert a2.stage == "near"

    # 25m: triggers now
    a3 = check_announcement(distance_to_next_m=25, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a3 is not None
    assert a3.stage == "now"


def test_stage_skipping_inside_near():
    """First sighting occurs at 90m (inside near). Skips far, emits near."""
    state = AnnouncementState()
    step = _step()
    speed = 8.0

    a = check_announcement(distance_to_next_m=90, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a is not None
    assert a.stage == "near"
    assert "far" not in state.announced_stages.values()


def test_stage_skipping_inside_now():
    """First sighting occurs at 20m (inside now). Skips far & near, emits now."""
    state = AnnouncementState()
    step = _step()
    speed = 8.0

    a = check_announcement(distance_to_next_m=20, speed_mps=speed, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a is not None
    assert a.stage == "now"
    assert state.announced_stages[1] == "now"


def test_gps_jitter_and_stop_and_go():
    """GPS jitter around near threshold (120m) and stop/go does not trigger duplicate announcements."""
    state = AnnouncementState()
    step = _step()

    # Move into near
    a1 = check_announcement(distance_to_next_m=110, speed_mps=5.0, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a1 is not None
    assert a1.stage == "near"

    # Jitter back to 130m (far region)
    a2 = check_announcement(distance_to_next_m=130, speed_mps=5.0, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a2 is None

    # Stop at red light (speed = 0) at 105m
    a3 = check_announcement(distance_to_next_m=105, speed_mps=0.0, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a3 is None


def test_off_route_suppresses_turns_and_announces_reroute_once():
    state = AnnouncementState()
    step = _step()

    # Off route
    a1 = check_announcement(distance_to_next_m=50, speed_mps=8.0, step_index=1, step=step, on_route=False, arrived=False, state=state)
    assert a1 is not None
    assert a1.stage == "reroute"
    assert a1.priority == "high"

    # Still off route
    a2 = check_announcement(distance_to_next_m=40, speed_mps=8.0, step_index=1, step=step, on_route=False, arrived=False, state=state)
    assert a2 is None

    # Back on route resets off_route_announced
    a3 = check_announcement(distance_to_next_m=100, speed_mps=8.0, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert a3 is not None
    assert a3.stage == "near"
    assert state.off_route_announced is False


def test_state_reset_on_reroute():
    state = AnnouncementState()
    step = _step()

    # Advance to now
    check_announcement(distance_to_next_m=20, speed_mps=8.0, step_index=1, step=step, on_route=True, arrived=False, state=state)
    assert 1 in state.announced_stages

    # Reroute triggers reset
    state.reset()
    assert len(state.announced_stages) == 0
    assert state.off_route_announced is False
    assert state.arrived_announced is False


def test_arrival_announcement_emitted_once():
    state = AnnouncementState()
    step = _step(maneuver="arrive", distance_m=0)

    a1 = check_announcement(distance_to_next_m=0, speed_mps=0.0, step_index=2, step=step, on_route=True, arrived=True, state=state)
    assert a1 is not None
    assert a1.stage == "arrival"
    assert a1.priority == "high"

    # Second arrival check
    a2 = check_announcement(distance_to_next_m=0, speed_mps=0.0, step_index=2, step=step, on_route=True, arrived=True, state=state)
    assert a2 is None
