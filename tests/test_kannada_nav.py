import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.schemas.route import Step
from app.services.intent.classifier import classify
from app.services.navigation.announcer import (
    AnnouncerConfig,
    AnnouncementState,
    build_arrival_announcement,
    build_driver_instruction,
    build_reroute_announcement,
    check_announcement,
    format_spoken_dist,
    round_spoken_distance,
)
from app.services.navigation.answers import fmt_dist_kn, next_kannada
from app.services.places.aliases import get_kannada_name


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


# -------------------------------------------------------------
# 1. KANNADA & KANGLISH INTENT RECOGNITION
# -------------------------------------------------------------
KANNADA_INTENT_CASES = [
    # Next turn - Kannada script & Kanglish
    ("ಮುಂದೆ ಎಲ್ಲಿ ತಿರುಗಬೇಕು?", ("next_turn", "kn")),
    ("ಎಲ್ಲಿ ತಿರುಗಬೇಕು", ("next_turn", "kn")),
    ("ಮುಂದಿನ ತಿರುವು ಏನು?", ("next_turn", "kn")),
    ("ಎಲ್ಲಿ ಹೋಗಬೇಕು", ("next_turn", "kn")),
    ("munde elli tirugabeku", ("next_turn", "kn")),
    ("munde elli thirugbeku", ("next_turn", "kn")),
    ("elli thirugbeku", ("next_turn", "kn")),
    ("yava kade hogbeku", ("next_turn", "kn")),
    ("munde enu", ("next_turn", "kn")),
    
    # On route - Kannada script & Kanglish
    ("ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೇನಾ?", ("on_route", "kn")),
    ("ಸರಿ ದಾರಿ", ("on_route", "kn")),
    ("ಸರಿಯಾದ ಮಾರ್ಗ", ("on_route", "kn")),
    ("ಸರಿಯಾಗಿ ಹೋಗ್ತಿದ್ದೀವಾ?", ("on_route", "kn")),
    ("sariyada dari", ("on_route", "kn")),
    ("sari dari", ("on_route", "kn")),
    ("sari hogtiddeeva", ("on_route", "kn")),
    ("sari hogtha iddeeva", ("on_route", "kn")),
    ("tappu dari", ("on_route", "kn")),

    # Time left (ETA) - Kannada script & Kanglish
    ("ಎಷ್ಟು ಸಮಯ ಬೇಕು?", ("time_left", "kn")),
    ("ಎಷ್ಟು ಹೊತ್ತು ಆಗುತ್ತೆ?", ("time_left", "kn")),
    ("ಎಷ್ಟು ನಿಮಿಷ ಬಾಕಿ ಇದೆ?", ("time_left", "kn")),
    ("eshtu samaya", ("time_left", "kn")),
    ("eshtu hottu", ("time_left", "kn")),
    ("eshtu nimisha", ("time_left", "kn")),
    ("eshtu time aagatte", ("time_left", "kn")),

    # Distance left - Kannada script & Kanglish
    ("ಇನ್ನು ಎಷ್ಟು ದೂರ?", ("distance_left", "kn")),
    ("ಎಷ್ಟು ದೂರ ಇದೆ?", ("distance_left", "kn")),
    ("ಎಷ್ಟು ಕಿಲೋಮೀಟರ್?", ("distance_left", "kn")),
    ("eshtu doora", ("distance_left", "kn")),
    ("innu eshtu doora", ("distance_left", "kn")),
    ("innu eshtu doora ide", ("distance_left", "kn")),

    # Arrived check - Kannada script & Kanglish
    ("ನಾವು ತಲುಪಿದ್ದೇವಾ?", ("arrived_check", "kn")),
    ("ತಲುಪಿದೆವಾ?", ("arrived_check", "kn")),
    ("ಜಾಗ ಬಂತಾ?", ("arrived_check", "kn")),
    ("ರೀಚ್ ಆಯ್ತಾ?", ("arrived_check", "kn")),
    ("talupiddheva", ("arrived_check", "kn")),
    ("talupidheva", ("arrived_check", "kn")),
    ("reach aaytha", ("arrived_check", "kn")),
    ("reach aytha", ("arrived_check", "kn")),
    ("jaaga bantha", ("arrived_check", "kn")),

    # Traffic ahead - Kannada script & Kanglish
    ("ಟ್ರಾಫಿಕ್ ಹೇಗಿದೆ?", ("traffic_ahead", "kn")),
    ("ಮುಂದೆ ಟ್ರಾಫಿಕ್ ಇದೆಯಾ?", ("traffic_ahead", "kn")),
    ("ರಸ್ತೆಯಲ್ಲಿ ಟ್ರಾಫಿಕ್ ಹೇಗಿದೆ?", ("traffic_ahead", "kn")),
    ("traffic hegide", ("traffic_ahead", "kn")),
    ("traffic hegidhe", ("traffic_ahead", "kn")),
    ("traffic ideya", ("traffic_ahead", "kn")),
    ("munde traffic ideya", ("traffic_ahead", "kn")),
    ("traffic jaasti ideya", ("traffic_ahead", "kn")),

    # Delay - Kannada script & Kanglish
    ("ಎಷ್ಟು ತಡವಾಗುತ್ತೆ?", ("delay", "kn")),
    ("ಡಿಲೇ ಎಷ್ಟಿದೆ?", ("delay", "kn")),
    ("ಎಷ್ಟು ಡಿಲೇ?", ("delay", "kn")),
    ("eshtu delay", ("delay", "kn")),
    ("eshtu tada", ("delay", "kn")),
    ("delay eshtide", ("delay", "kn")),
    ("eshtu late aagatte", ("delay", "kn")),

    # Incident - Kannada script & Kanglish
    ("ಯಾವುದಾದರೂ ಅಪಘಾತ ಆಗಿದೆಯಾ?", ("incident", "kn")),
    ("ರಸ್ತೆ ಬಂದ್ ಆಗಿದೆಯಾ?", ("incident", "kn")),
    ("ಅಪಘಾತ ಏನಾದರೂ ಇದೆಯಾ?", ("incident", "kn")),
    ("accident aagidiya", ("incident", "kn")),
    ("accident aagidheya", ("incident", "kn")),
    ("raste band agidiya", ("incident", "kn")),
    ("yenadru accident", ("incident", "kn")),

    # Repeat - Kannada script & Kanglish
    ("ಮತ್ತೆ ಹೇಳಿ", ("repeat", "kn")),
    ("ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ", ("repeat", "kn")),
    ("ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ", ("repeat", "kn")),
    ("ಇನ್ನೊಂದು ಸಲ ಹೇಳಿ", ("repeat", "kn")),
    ("matte heli", ("repeat", "kn")),
    ("innomme heli", ("repeat", "kn")),
    ("innondhu sala heli", ("repeat", "kn")),
]


def test_kannada_intent_classification():
    for text, expected in KANNADA_INTENT_CASES:
        actual = classify(text)
        assert actual == expected, f"Failed on '{text}': expected {expected}, got {actual}"


# -------------------------------------------------------------
# 2. KANNADA DRIVER PHRASING & REGULATORY WORD LIMIT
# -------------------------------------------------------------
def test_kannada_driver_phrasing_rules():
    config = AnnouncerConfig(enable_kannada_driver=True)
    step = _step(maneuver="turn", modifier="left", road="CMH Road")

    # Far stage
    far_phrase = build_driver_instruction(
        stage="far",
        step=step,
        distance_to_next_m=400,
        lang="kn",
        config=config,
    )
    assert len(far_phrase.split()) <= 12
    assert far_phrase.endswith(".")
    assert "ಮೀಟರ್" in far_phrase
    assert "ಎಡಕ್ಕೆ ತಿರುಗಿ" in far_phrase

    # Near stage with landmark
    near_phrase = build_driver_instruction(
        stage="near",
        step=step,
        distance_to_next_m=120,
        landmark_name="Sir Puttanna Chetty Town Hall",
        lang="kn",
        config=config,
    )
    assert len(near_phrase.split()) <= 12
    assert near_phrase.endswith(".")
    assert "ಪುಟ್ಟಣ್ಣ ಚೆಟ್ಟಿ ಪುರಭವನ" in near_phrase  # Canonical Kannada landmark applied
    assert "ಹತ್ತಿರ" in near_phrase

    # Now stage
    now_phrase = build_driver_instruction(
        stage="now",
        step=step,
        distance_to_next_m=20,
        lang="kn",
        config=config,
    )
    assert len(now_phrase.split()) <= 12
    assert now_phrase == "ಈಗ ಎಡಕ್ಕೆ ತಿರುಗಿ."


def test_kannada_driver_maneuvers():
    config = AnnouncerConfig(enable_kannada_driver=True)

    maneuvers = [
        ("turn", "right", "ಬಲಕ್ಕೆ ತಿರುಗಿ", "ಈಗ ಬಲಕ್ಕೆ ತಿರುಗಿ."),
        ("turn", "slight left", "ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ ಇರಿ", "ಈಗ ಸ್ವಲ್ಪ ಎಡಕ್ಕೆ ಇರಿ."),
        ("turn", "slight right", "ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ ಇರಿ", "ಈಗ ಸ್ವಲ್ಪ ಬಲಕ್ಕೆ ಇರಿ."),
        ("turn", "sharp left", "ಪೂರ್ತಿ ಎಡಕ್ಕೆ ತಿರುಗಿ", "ಈಗ ಪೂರ್ತಿ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
        ("turn", "sharp right", "ಪೂರ್ತಿ ಬಲಕ್ಕೆ ತಿರುಗಿ", "ಈಗ ಪೂರ್ತಿ ಬಲಕ್ಕೆ ತಿರುಗಿ."),
        ("turn", "uturn", "ಯು-ಟರ್ನ್ ತೆಗೆದುಕೊಳ್ಳಿ", "ಈಗ ಯು-ಟರ್ನ್ ತೆಗೆದುಕೊಳ್ಳಿ."),
        ("roundabout", None, "ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ", "ಈಗ ರೌಂಡ್‌ಅಬೌಟ್ ತೆಗೆದುಕೊಳ್ಳಿ."),
        ("fork", "left", "ಎಡ ಬದಿಯಲ್ಲಿ ಇರಿ", "ಈಗ ಎಡ ಬದಿಯಲ್ಲಿ ಇರಿ."),
        ("fork", "right", "ಬಲ ಬದಿಯಲ್ಲಿ ಇರಿ", "ಈಗ ಬಲ ಬದಿಯಲ್ಲಿ ಇರಿ."),
        ("depart", None, "ಪ್ರಯಾಣ ಪ್ರಾರಂಭಿಸಿ", "ಈಗ ನೇರವಾಗಿ ಹೋಗಿ."),
    ]

    for man, mod, expected_action, expected_now in maneuvers:
        step = _step(maneuver=man, modifier=mod, road="MG Road")
        
        # Test near stage
        near = build_driver_instruction(stage="near", step=step, distance_to_next_m=100, lang="kn", config=config)
        assert len(near.split()) <= 12
        if man != "depart":
            assert expected_action in near

        # Test now stage
        now = build_driver_instruction(stage="now", step=step, distance_to_next_m=20, lang="kn", config=config)
        assert len(now.split()) <= 12
        assert now == expected_now


def test_kannada_arrival_and_reroute():
    config = AnnouncerConfig(enable_kannada_driver=True)

    arr = build_arrival_announcement("kn", config)
    assert arr.text == "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ."
    assert len(arr.text.split()) <= 12
    assert arr.language == "kn"
    assert arr.stage == "arrival"

    reroute = build_reroute_announcement("kn", config)
    assert reroute.text == "ದಾರಿಯಿಂದ ಹೊರಗಿದ್ದೀರಿ, ಹೊಸ ದಾರಿ ಹುಡುಕುತ್ತಿದ್ದೇವೆ."
    assert len(reroute.text.split()) <= 12
    assert reroute.language == "kn"
    assert reroute.stage == "reroute"


# -------------------------------------------------------------
# 3. KANNADA DISTANCE FORMATTING & CANONICAL ALIASES
# -------------------------------------------------------------
def test_kannada_distance_formatting():
    # Spoken driver buckets (< 900m)
    assert format_spoken_dist(50, "m", "kn") == "50 ಮೀಟರ್"
    assert format_spoken_dist(100, "m", "kn") == "100 ಮೀಟರ್"
    assert format_spoken_dist(400, "m", "kn") == "400 ಮೀಟರ್"
    assert format_spoken_dist(800, "m", "kn") == "800 ಮೀಟರ್"
    assert format_spoken_dist(1.0, "km", "kn") == "1 ಕಿಲೋಮೀಟರ್"
    assert format_spoken_dist(2.5, "km", "kn") == "2.5 ಕಿಲೋಮೀಟರ್"

    # Conversational roundings
    assert fmt_dist_kn(70) == "70 ಮೀಟರ್"
    assert fmt_dist_kn(320) == "320 ಮೀಟರ್"
    assert fmt_dist_kn(1500) == "1.5 ಕಿಲೋಮೀಟರ್"


def test_kannada_canonical_landmarks():
    assert get_kannada_name("Indiranagar Metro Station") == "ಇಂದಿರಾನಗರ ಮೆಟ್ರೋ ನಿಲ್ದಾಣ"
    assert get_kannada_name("Sir Puttanna Chetty Town Hall") == "ಪುಟ್ಟಣ್ಣ ಚೆಟ್ಟಿ ಪುರಭವನ"
    assert get_kannada_name("Bangalore Palace") == "ಬೆಂಗಳೂರು ಅರಮನೆ"
    assert get_kannada_name("Central Silk Board") == "ಸೆಂಟ್ರಲ್ ಸಿಲ್ಕ್ ಬೋರ್ಡ್"
    assert get_kannada_name("Marathahalli") == "ಮಾರತ್‌ಹಳ್ಳಿ"
    assert get_kannada_name("Whitefield") == "ವೈಟ್‌ಫೀಲ್ಡ್"
    assert get_kannada_name("Electronic City") == "ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಿಟಿ"
    assert get_kannada_name("Banashankari") == "ಬನಶಂಕರಿ"
    assert get_kannada_name("HSR Layout") == "ಹೆಚ್ ಎಸ್ ಆರ್ ಲೇಔಟ್"
    assert get_kannada_name("BTM Layout") == "ಬಿ ಟಿ ಎಂ ಲೇಔಟ್"


def test_next_kannada_conversational():
    step = _step(maneuver="turn", modifier="right", road="100 Feet Road")
    
    # Without landmark
    res1 = next_kannada(step, 150, None)
    assert res1 == "150 ಮೀಟರ್ ನಂತರ 100 Feet Road ನಲ್ಲಿ ಬಲಕ್ಕೆ ತಿರುಗಿ."

    # With landmark (resolved to authentic Kannada name)
    res2 = next_kannada(step, 200, "Sir Puttanna Chetty Town Hall")
    assert res2 == "200 ಮೀಟರ್ ನಂತರ 100 Feet Road ನಲ್ಲಿ ಬಲಕ್ಕೆ ತಿರುಗಿ, ಪುಟ್ಟಣ್ಣ ಚೆಟ್ಟಿ ಪುರಭವನ ಹತ್ತಿರ."
