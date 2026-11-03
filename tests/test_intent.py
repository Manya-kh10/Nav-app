import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.intent.classifier import classify

CASES = [
    # English
    ("Where do I turn next?", ("next_turn", "en")),
    ("where do i trun next", ("next_turn", "en")),
    ("where to turn next", ("next_turn", "en")),
    ("Am I on the right path?", ("on_route", "en")),
    ("how long will it take", ("time_left", "en")),
    ("how far is it", ("distance_left", "en")),
    ("repeat that", ("repeat", "en")),
    ("are we there yet", ("arrived_check", "en")),
    # Hinglish, including real speech-recognition output
    ("Ab mujhe kahan mudna hai?", ("next_turn", "hinglish")),
    ("ab kahaan turn lena hai", ("next_turn", "hinglish")),
    ("ab kahaan paanch lena hai", ("next_turn", "hinglish")),
    ("Kya main sahi raste par hoon?", ("on_route", "hinglish")),
    ("kya main sahi ja rahi hu", ("on_route", "hinglish")),
    ("Kitna time lagega?", ("time_left", "hinglish")),
    ("aur kitna time lagega", ("time_left", "hinglish")),
    ("kya hum pahunch gaye", ("arrived_check", "hinglish")),
    # should not match anything
    ("tell me a joke", ("unknown", "en")),
    ("what is the weather today", ("unknown", "en")),
]


def test_classify():
    for text, expected in CASES:
        assert classify(text) == expected, text