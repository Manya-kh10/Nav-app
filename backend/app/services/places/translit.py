"""Rough Devanagari / Kannada -> Latin transliteration.
Used only to generate match candidates, never as proof that two names are the same."""
import re

# Kannada code points sit exactly 0x380 above their Devanagari twins, so one table serves both.
_DIGITS = {**{0x966 + i: str(i) for i in range(10)}, **{0xCE6 + i: str(i) for i in range(10)}}

_VOWELS = {0x905: "a", 0x906: "aa", 0x907: "i", 0x908: "ee", 0x909: "u", 0x90A: "oo", 0x90B: "ri",
           0x90D: "e", 0x90E: "e", 0x90F: "ee", 0x910: "ai", 0x911: "o", 0x912: "o", 0x913: "oo",
           0x914: "au"}
_MATRAS = {0x93E: "aa", 0x93F: "i", 0x940: "ee", 0x941: "u", 0x942: "oo", 0x943: "ri", 0x945: "e",
           0x946: "e", 0x947: "ee", 0x948: "ai", 0x949: "o", 0x94A: "o", 0x94B: "oo", 0x94C: "au"}
_CONS = {0x915: "k", 0x916: "kh", 0x917: "g", 0x918: "gh", 0x919: "n", 0x91A: "ch", 0x91B: "chh",
         0x91C: "j", 0x91D: "jh", 0x91E: "n", 0x91F: "t", 0x920: "th", 0x921: "d", 0x922: "dh",
         0x923: "n", 0x924: "t", 0x925: "th", 0x926: "d", 0x927: "dh", 0x928: "n", 0x92A: "p",
         0x92B: "ph", 0x92C: "b", 0x92D: "bh", 0x92E: "m", 0x92F: "y", 0x930: "r", 0x931: "r",
         0x932: "l", 0x933: "l", 0x935: "v", 0x936: "sh", 0x937: "sh", 0x938: "s", 0x939: "h",
         0x958: "k", 0x959: "kh", 0x95A: "g", 0x95B: "j", 0x95C: "d", 0x95D: "dh", 0x95E: "f",
         0x95F: "y"}
_VIRAMA = 0x94D
_NUKTA = 0x93C
_ANUSVARA = {0x901, 0x902}
_VISARGA = 0x903
_LABIALS = {0x92A, 0x92B, 0x92C, 0x92D, 0x92E}

# Whole-word English loanwords as speech models usually write them. Starter list:
# extend it with what Prisma actually returns.
LOANWORDS = {
    # Hindi (Devanagari)
    "मेट्रो": "metro", "स्टेशन": "station", "रेलवे": "railway", "बस": "bus", "स्टैंड": "stand",
    "स्टैण्ड": "stand", "मॉल": "mall", "अस्पताल": "hospital", "हॉस्पिटल": "hospital",
    "रोड": "road", "सर्कल": "circle", "चौराहा": "circle", "मार्केट": "market", "बाजार": "market",
    "बाज़ार": "market", "मंदिर": "temple", "कॉलेज": "college", "स्कूल": "school",
    "पार्क": "park", "जंक्शन": "junction", "लेआउट": "layout", "क्रॉस": "cross",
    "एयरपोर्ट": "airport", "मजेस्टिक": "majestic", "मैजेस्टिक": "majestic", "केआर": "kr",
    "के": "k", "आर": "r",
    # Kannada
    "ಮೆಟ್ರೋ": "metro", "ಸ್ಟೇಷನ್": "station", "ಸ್ಟೇಶನ್": "station", "ಬಸ್": "bus",
    "ನಿಲ್ದಾಣ": "station", "ಸ್ಟ್ಯಾಂಡ್": "stand", "ಮಾಲ್": "mall", "ಆಸ್ಪತ್ರೆ": "hospital",
    "ಹಾಸ್ಪಿಟಲ್": "hospital", "ರಸ್ತೆ": "road", "ರೋಡ್": "road", "ಸರ್ಕಲ್": "circle",
    "ವೃತ್ತ": "circle", "ಮಾರುಕಟ್ಟೆ": "market", "ಮಾರ್ಕೆಟ್": "market", "ದೇವಸ್ಥಾನ": "temple",
    "ದೇವಾಲಯ": "temple", "ಕಾಲೇಜು": "college", "ಕಾಲೇಜ್": "college", "ಶಾಲೆ": "school",
    "ಸ್ಕೂಲ್": "school", "ಪಾರ್ಕ್": "park", "ಉದ್ಯಾನ": "park", "ಜಂಕ್ಷನ್": "junction",
    "ಲೇಔಟ್": "layout", "ಬಡಾವಣೆ": "layout", "ಕ್ರಾಸ್": "cross", "ಮೆಜೆಸ್ಟಿಕ್": "majestic",
    "ಕೆಆರ್": "kr", "ಕೆ": "k", "ಆರ್": "r",
}


def _is_indic(ch: str) -> bool:
    o = ord(ch)
    return 0x900 <= o <= 0x97F or 0xC80 <= o <= 0xCFF


def _word_to_latin(word: str) -> str:
    cps = []
    for ch in word:
        o = ord(ch)
        if 0xC80 <= o <= 0xCFF:
            o -= 0x380
        cps.append(o)
    out: list[str] = []
    n = len(cps)
    i = 0
    while i < n:
        cp = cps[i]
        if cp in _CONS:
            roman = _CONS[cp]
            j = i + 1
            if j < n and cps[j] == _NUKTA:
                j += 1
            nxt = cps[j] if j < n else None
            if nxt == _VIRAMA:
                out.append(roman)
                i = j + 1
                continue
            if nxt in _MATRAS:
                out.append(roman + _MATRAS[nxt])
                i = j + 1
                continue
            out.append(roman + "a")
            i = j
            continue
        if cp in _VOWELS:
            out.append(_VOWELS[cp])
        elif cp in _ANUSVARA:
            nxt = cps[i + 1] if i + 1 < n else None
            out.append("m" if nxt in _LABIALS else "n")
        elif cp == _VISARGA:
            out.append("h")
        elif cp in _MATRAS or cp in (_VIRAMA, _NUKTA):
            pass
        else:
            out.append(chr(cp))
        i += 1
    s = "".join(out)
    return re.sub(r"(?<=[bcdfghjklmnpqrstvwxyz])a$", "", s)  # drop the final inherent "a"


def to_latin(text: str) -> str:
    words = []
    for w in text.split():
        bare = w.strip("।॥.,?!;:'\"()")
        if bare in LOANWORDS:
            words.append(LOANWORDS[bare])
        elif any(_is_indic(c) for c in bare):
            words.append(_word_to_latin(bare.translate(_DIGITS)))
        else:
            words.append(w)
    return " ".join(words)
