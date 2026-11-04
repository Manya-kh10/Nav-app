import re

from rapidfuzz import fuzz

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_KANNADA = re.compile(r"[\u0C80-\u0CFF]")

FUZZY_MIN_LEN = 10   # only phrases at least this long get typo tolerance
FUZZY_SCORE = 90


def _collapse(s: str) -> str:
    """Collapse repeated letters so spelling variants match (kahaan = kahan, theek = thek)."""
    return re.sub(r"(\w)\1+", r"\1", s)


def _norm(text: str) -> str:
    return _collapse(re.sub(r"[^\w\u0900-\u097F\u0C80-\u0CFF]+", " ", text.lower()).strip())


def _s(*words: str) -> set[str]:
    return {_collapse(w) for w in words}


_HINGLISH = _s(
    "kya", "mujhe", "kahan", "kaha", "kidhar", "kitna", "kitni", "kitne", "mudna", "modna",
    "mudun", "sahi", "galat", "raste", "rasta", "hoon", "hun", "hu", "hai", "ab", "lagega",
    "lagegi", "kab", "aap", "mera", "samay", "phir", "dobara", "bolo", "batao", "bataiye",
    "agla", "pahunch", "rahi", "raha", "theek", "jana", "jaun", "hum", "gaye", "gaya", "gayi",
    "lena", "chalna", "aur", "manzil", "aage", "band", "halka", "dhoond",
)

_KANGLISH = _s(
    "munde", "elli", "tiruga", "tirugabeku", "yava", "kade", "doora", "eshtu", "hottu",
    "samaya", "nimisha", "dari", "sari", "sariyada", "tappu", "talupiddheva", "talupidheva",
    "talupidena", "bantha", "banta", "matte", "heli", "hogabeku", "muttidheva", "innomme",
    "hegide", "ideya", "tada",
)

# order matters: first matching intent wins
RULES = [
    ("repeat", [
        "repeat", "say that again", "say again", "once more", "again", "what did you say",
        "dobara", "phir se", "ek baar aur", "repeat karo", "फिर से", "दोबारा", "दुबारा",
        "ಮತ್ತೆ ಹೇಳಿ", "ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ", "ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ", "ಏನ್ ಹೇಳಿದ್ರಿ", "matte heli", "innomme heli",
    ]),
    ("incident", [
        "any incident", "any accidents", "any accident", "any crash", "road closed", "road blocked",
        "road works", "construction ahead", "accident ahead", "jam ahead",
        "koi accident", "accident hua hai kya", "road band hai kya", "koi jam hai kya",
        "koi incident", "traffic jam ahead", "aage koi jam",
        "ಯಾವುದಾದರೂ ಅಪಘಾತ", "ರಸ್ತೆ ಬಂದ್ ಆಗಿದೆಯಾ", "ಅಪಘಾತವಾಗಿದೆಯಾ", "ಯಾವುದಾದರೂ ಜಾಮ್ ಇದೆಯಾ",
        "accident aagidiya", "raste band agidiya",
    ]),
    ("delay", [
        "how much delay", "traffic delay", "any delay", "is there any delay", "how late",
        "kitna delay", "delay kitna hai", "kitna der hoga", "traffic delay kitna hai",
        "कितना डिले", "कितना लेट", "कितनी देरी",
        "ಎಷ್ಟು ತಡ", "ಎಷ್ಟು ಡಿಲೇ", "ಡಿಲೇ ಎಷ್ಟಿದೆ", "eshtu delay", "eshtu tada",
    ]),
    ("traffic_ahead", [
        "how is the traffic", "how is traffic", "is there traffic", "traffic condition",
        "traffic ahead", "any traffic", "traffic update", "traffic report", "is traffic heavy",
        "traffic kaisa hai", "aage traffic kaisa hai", "traffic kaisa", "aage traffic hai kya",
        "traffic hai kya", "kitna traffic hai", "traffic kaisa h", "ट्रैफिक कैसा है", "आगे ट्रैफिक कैसा है",
        "ಟ್ರಾಫಿಕ್ ಹೇಗಿದೆ", "ಟ್ರಾಫಿಕ್ ಇದೆಯಾ", "ಮುಂದೆ ಟ್ರಾಫಿಕ್ ಇದೆಯಾ", "ಟ್ರಾಫಿಕ್ ಪರಿಸ್ಥಿತಿ ಏನು",
        "traffic hegide", "traffic ideya", "munde traffic ideya",
    ]),
    ("arrived_check", [
        "have i arrived", "have we arrived", "did i arrive", "are we there", "am i there",
        "pahunch gaye", "pahunch gaya", "pahunch gayi", "pahunch gye", "reach gaye",
        "reach gaya", "reach gayi", "manzil aa gayi", "manzil aa gaya", "manzil pahunch",
        "पहुँच गए", "पहुंच गए", "पहुँच गया", "पहुंच गया",
        "ತಲುಪಿದ್ದೇವಾ", "ತಲುಪಿದೆವಾ", "ಮುಟ್ಟಿದ್ದೇವಾ", "ತಲುಪಿದಿವಾ", "ಬಂತಾ", "ಜಾಗ ಬಂತಾ",
        "talupiddheva", "talupidheva", "bantha", "jaaga bantha",
    ]),
    ("on_route", [
        "right track", "right path", "right route", "right way", "right direction",
        "correct way", "correct route", "on route", "on the route", "on track", "am i lost",
        "wrong way", "wrong turn", "going the right way",
        "sahi raste", "sahi rasta", "sahi route", "sahi disha", "sahi direction", "sahi ja",
        "sahi jaa", "theek raste", "theek ja", "galat raste", "galat rasta", "galat ja",
        "galat direction", "सही रास्ते", "सही रास्ता", "सही जा", "गलत रास्ते",
        "ಸರಿಯಾದ ದಾರಿ", "ಸರಿ ದಾರಿ", "ಸರಿಯಾದ ಮಾರ್ಗ", "ಸರಿ ದಾರಿನಾ", "ತಪ್ಪು ದಾರಿ",
        "sariyada dari", "sari dari", "tappu dari", "sariyada marga",
    ]),
    ("time_left", [
        "how long", "how much time", "time left", "minutes left", "how many minutes", "eta",
        "when will i reach", "when do i arrive", "kitna time", "kitni der", "kitna samay",
        "kab tak", "kab pahunch", "कितना समय", "कितनी देर",
        "ಎಷ್ಟು ಸಮಯ", "ಎಷ್ಟು ಹೊತ್ತು", "ಎಷ್ಟು ನಿಮಿಷ", "ಎಷ್ಟು ಟೈಮ್",
        "eshtu samaya", "eshtu hottu", "eshtu nimisha", "eshtu time",
    ]),
    ("distance_left", [
        "how far", "how many meters", "how many metres", "how many km", "how many kilometers",
        "distance left", "remaining distance", "kitni door", "kitna door", "kitne meter",
        "kitne km", "कितनी दूर",
        "ಎಷ್ಟು ದೂರ", "ಇನ್ನು ಎಷ್ಟು ದೂರ", "ಎಷ್ಟು ಮೀಟರ್", "ಎಷ್ಟು ಕಿಮಿ",
        "eshtu doora", "innu eshtu doora", "eshtu meter", "eshtu km",
    ]),
    ("next_turn", [
        "next turn", "where do i turn", "where should i turn", "where to turn", "which way",
        "what next", "what now", "next instruction", "turn next", "left or right",
        "next left", "next right", "kahan mudna", "kahan modna", "kahan mudun",
        "kidhar mudna", "kidhar modna", "kidhar turn", "kahan turn", "ab mujhe kahan",
        "agla mod", "ab kya karna", "kya karna hai", "mudna hai", "modna hai",
        "अगला मोड़", "कहाँ मुड़", "कहां मुड़", "किधर मुड़",
        "ಮುಂದೆ ಎಲ್ಲಿ ತಿರುಗಬೇಕು", "ಎಲ್ಲಿ ತಿರುಗಬೇಕು", "ಮುಂದಿನ ತಿರುವು", "ಮುಂದೆ ಏನು", "ಎಲ್ಲಿ ಹೋಗಬೇಕು", "ಯಾವ ಕಡೆ",
        "munde elli tirugabeku", "elli tirugabeku", "munde enu", "yava kade", "elli hogabeku",
    ]),
]
_RULES = [(intent, [_collapse(p.lower()) for p in phrases]) for intent, phrases in RULES]

# Fallback when no phrase matches: one anchor word from each group is enough.
COMBOS = [
    ("traffic_ahead", _s("traffic"), _s("kaisa", "hai", "ahead", "update", "condition", "status", "kitna", "hegide", "ideya")),
    ("delay", _s("delay"), _s("kitna", "kitni", "traffic", "how", "much", "eshtu", "tada", "is", "there")),
    ("incident", _s("accident", "jam", "blocked", "closed"), _s("any", "is", "koi", "ahead", "aage", "band")),
    ("next_turn", _s("kahan", "kidhar", "kaha"),
     _s("mudna", "modna", "mudun", "modun", "turn", "lena", "lun", "jaun", "jana", "chalna", "mod")),
    ("next_turn", _s("where"), _s("turn", "go", "next", "left", "right")),
    ("next_turn", _s("elli", "yava", "munde", "ಎಲ್ಲಿ", "ಯಾವ", "ಮುಂದೆ"),
     _s("tirugabeku", "tiruga", "hogabeku", "hoga", "kade", "ತಿರುಗಬೇಕು", "ತಿರುಗಿ", "ಹೋಗಬೇಕು", "ಕಡೆ", "ತಿರುವು")),
    ("time_left", _s("kitna", "kitni", "kitne"), _s("time", "der", "samay", "minute", "min")),
    ("time_left", _s("eshtu", "ಎಷ್ಟು"), _s("samaya", "hottu", "nimisha", "time", "ಸಮಯ", "ಹೊತ್ತು", "ನಿಮಿಷ", "ಟೈಮ್")),
    ("distance_left", _s("kitna", "kitni", "kitne"), _s("door", "dur", "meter", "km", "kilometer")),
    ("distance_left", _s("eshtu", "ಎಷ್ಟು"), _s("doora", "dur", "meter", "km", "ದೂರ", "ಮೀಟರ್", "ಕಿಮಿ")),
    ("on_route", _s("sahi", "theek", "galat"),
     _s("raste", "rasta", "route", "ja", "jana", "jaa", "disha", "direction", "side", "taraf")),
    ("on_route", _s("sari", "sariyada", "tappu", "ಸರಿ", "ಸರಿಯಾದ", "ತಪ್ಪು"),
     _s("dari", "dharina", "marga", "raste", "route", "ದಾರಿ", "ದಾರಿನಾ", "ಮಾರ್ಗ", "ರಸ್ತೆ")),
]


def _has(norm: str, phrase: str) -> bool:
    if not phrase.isascii():
        return phrase in norm
    if f" {phrase} " in f" {norm} ":
        return True
    if len(phrase) >= FUZZY_MIN_LEN:
        return fuzz.partial_ratio(phrase, norm) >= FUZZY_SCORE
    return False


def detect_lang(text: str, norm: str) -> str:
    if _KANNADA.search(text):
        return "kn"
    if _DEVANAGARI.search(text):
        return "hinglish"
    words = set(norm.split())
    if words & _KANGLISH:
        return "kn"
    if words & _HINGLISH:
        return "hinglish"
    return "en"


def classify(text: str) -> tuple[str, str]:
    norm = _norm(text)
    lang = detect_lang(text, norm)

    for intent, phrases in _RULES:
        for p in phrases:
            if _has(norm, p):
                return intent, lang

    words = set(norm.split())
    for intent, a, b in COMBOS:
        if (words & a) and (words & b):
            return intent, lang

    return "unknown", lang
