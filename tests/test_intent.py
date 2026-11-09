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
    ("how is the traffic", ("traffic_ahead", "en")),
    ("is there traffic ahead", ("traffic_ahead", "en")),
    ("how much traffic delay", ("delay", "en")),
    ("any accidents ahead", ("incident", "en")),
    ("repeat that", ("repeat", "en")),
    ("are we there yet", ("arrived_check", "en")),
    ("how long do i have to walk", ("time_left", "en")),
    ("how far do i have to walk", ("distance_left", "en")),
    ("start", ("start_navigation", "en")),
    # Hinglish, including real speech-recognition output
    ("Ab mujhe kahan mudna hai?", ("next_turn", "hinglish")),
    ("ab kahaan turn lena hai", ("next_turn", "hinglish")),
    ("ab kahaan paanch lena hai", ("next_turn", "hinglish")),
    ("Kya main sahi raste par hoon?", ("on_route", "hinglish")),
    ("kya main sahi ja rahi hu", ("on_route", "hinglish")),
    ("Kitna time lagega?", ("time_left", "hinglish")),
    ("aur kitna time lagega", ("time_left", "hinglish")),
    ("kitna chalna padega", ("time_left", "hinglish")),
    ("कितना चलना पड़ेगा मुझे", ("time_left", "hi")),
    ("और कितना time लगेगा", ("time_left", "hinglish")),
    ("क्या यह turn सही है", ("on_route", "hinglish")),
    ("अब मैं कहाँ जाऊँ", ("next_turn", "hi")),
    ("abhi aur kitani there chalana hai", ("time_left", "hinglish")),
    ("chalo", ("start_navigation", "hinglish")),
    ("kya hum pahunch gaye", ("arrived_check", "hinglish")),
    ("traffic kaisa hai", ("traffic_ahead", "hinglish")),
    ("aage traffic hai kya", ("traffic_ahead", "hinglish")),
    ("kitna delay hai", ("delay", "hinglish")),
    ("aage koi accident hai kya", ("incident", "hinglish")),
    # Kannada (Script and Kanglish)
    ("ಮುಂದೆ ಎಲ್ಲಿ ತಿರುಗಬೇಕು?", ("next_turn", "kn")),
    ("ಎಲ್ಲಿ ತಿರುಗಬೇಕು", ("next_turn", "kn")),
    ("ಸರಿಯಾದ ದಾರಿಯಲ್ಲಿದ್ದೇನಾ?", ("on_route", "kn")),
    ("ಸರಿ ದಾರಿ", ("on_route", "kn")),
    ("ಎಷ್ಟು ಸಮಯ ಬೇಕು?", ("time_left", "kn")),
    ("ಎಷ್ಟು ನಡೆಯಬೇಕು?", ("time_left", "kn")),
    ("eshtu nadeyabeku", ("time_left", "kn")),
    ("eshtu doora nadeyabeku", ("distance_left", "kn")),
    ("ಪ್ರಾರಂಭಿಸಿ", ("start_navigation", "kn")),
    ("ಇನ್ನು ಎಷ್ಟು ದೂರ?", ("distance_left", "kn")),
    ("ಮತ್ತೆ ಹೇಳಿ", ("repeat", "kn")),
    ("ತಲುಪಿದ್ದೇವಾ?", ("arrived_check", "kn")),
    ("ಟ್ರಾಫಿಕ್ ಹೇಗಿದೆ", ("traffic_ahead", "kn")),
    ("traffic hegide", ("traffic_ahead", "kn")),
    ("eshtu delay", ("delay", "kn")),
    ("munde elli tirugabeku", ("next_turn", "kn")),
    ("sariyada dari", ("on_route", "kn")),
    ("eshtu samaya", ("time_left", "kn")),
    ("eshtu doora", ("distance_left", "kn")),
    ("matte heli", ("repeat", "kn")),
    # should not match anything
    ("tell me a joke", ("unknown", "en")),
    ("what is the weather today", ("unknown", "en")),
]


def test_classify():
    for text, expected in CASES:
        actual = classify(text)
        assert actual == expected, f"Failed on '{text}': expected {expected}, got {actual}"
