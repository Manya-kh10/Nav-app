"""Bangalore colloquial place aliases.
Maps common local names (Majestic, KR Market, Silk Board) to canonical OSM names and vice versa.
"""
import re


def norm_alias(s: str) -> str:
    """Normalize alias with character collapse matching matcher's make_key."""
    clean = re.sub(r"[^a-z0-9]+", "", s.lower())
    return re.sub(r"(.)\1+", r"\1", clean)


# Canonical name -> list of colloquial alias names
CANONICAL_ALIASES: dict[str, list[str]] = {
    "Kempegowda Bus Station": [
        "majestic bus stand", "majestic bus station", "majestic stand",
        "majestic bus stop", "majestic", "kbs",
    ],
    "Nadaprabhu Kempegowda Station, Majestic": [
        "majestic metro", "majestic metro station", "majestic subway", "majestic train station",
    ],
    "Krishna Rajendra Market": [
        "kr market", "k r market", "city market", "kr market metro",
    ],
    "KR Market Bus Terminus": [
        "kr market bus stand", "kr market bus stop", "kr market stand",
    ],
    "Central Silk Board": [
        "silk board", "silkboard", "silk board junction", "silk board bus stop",
    ],
    "Sir Puttanna Chetty Town Hall": [
        "town hall", "bangalore town hall", "town hall circle",
    ],
    "Benniganahalli": [
        "tin factory", "tin factory bus stop", "tin factory junction",
    ],
    "Hudson Circle": [
        "corporation", "corporation circle", "bbmp head office",
    ],
    "Bangalore Cantonment": [
        "cantonment", "cantonment railway station", "bangalore cantt", "cantonment station",
    ],
    "KSR Bengaluru City Railway Station": [
        "city railway station", "bangalore city railway station", "sangolli rayanna station",
        "majestic railway station",
    ],
    "Mysuru Road Satellite Bus Station": [
        "satellite bus stand", "mysore road satellite bus stand", "mrsbs",
    ],
    "Shanti Nagar Bus Station": [
        "shantinagar bus stand", "shanti nagar bus stand", "shantinagar stand",
    ],
    "Shivajinagar Bus Station": [
        "shivajinagar bus stand", "shivaji nagar bus stand", "shivajinagar stand",
    ],
    "Prof CNR Rao Circle": [
        "mekhri circle", "mekhri circle junction",
    ],
    "Mahatma Gandhi Road": [
        "mg road", "mg road metro", "mg road metro station", "m g road", "mg road station",
    ],
    "Nexus Koramangala": [
        "forum mall", "forum mall koramangala", "koramangala forum", "forum koramangala",
    ],
}

# Reverse mapping: normalized alias key -> canonical name
QUERY_ALIASES: dict[str, str] = {}
for canonical, aliases in CANONICAL_ALIASES.items():
    for alias in aliases:
        k = norm_alias(alias)
        QUERY_ALIASES[k] = canonical


# Prominent Bangalore landmarks that may be missing or differently tagged in raw OSM POIs
PROMINENT_PLACES: list[dict] = [
    {
        "name": "Sir Puttanna Chetty Town Hall",
        "name_en": "Sir Puttanna Chetty Town Hall",
        "name_kn": "ಪುಟ್ಟಣ್ಣ ಚೆಟ್ಟಿ ಪುರಭವನ",
        "kind": "townhall",
        "lat": 12.9633,
        "lon": 77.5833,
    },
    {
        "name": "Bangalore Palace",
        "name_en": "Bangalore Palace",
        "name_kn": "ಬೆಂಗಳೂರು ಅರಮನೆ",
        "kind": "attraction",
        "lat": 12.9988,
        "lon": 77.5921,
    },
]

# Canonical Kannada name dictionary for high-frequency destinations
CANONICAL_KN: dict[str, str] = {
    "Indiranagar Metro Station": "ಇಂದಿರಾನಗರ ಮೆಟ್ರೋ ನಿಲ್ದಾಣ",
    "Indiranagar": "ಇಂದಿರಾನಗರ",
    "Kempegowda Bus Station": "ಕೆಂಪೇಗೌಡ ಬಸ್ ನಿಲ್ದಾಣ",
    "Nadaprabhu Kempegowda Station, Majestic": "ಮೆಜೆಸ್ಟಿಕ್ ಮೆಟ್ರೋ ನಿಲ್ದಾಣ",
    "Krishna Rajendra Market": "ಕೃಷ್ಣರಾಜೇಂದ್ರ ಮಾರುಕಟ್ಟೆ",
    "KR Market Bus Terminus": "ಕೃಷ್ಣರಾಜೇಂದ್ರ ಮಾರುಕಟ್ಟೆ ಬಸ್ ನಿಲ್ದಾಣ",
    "Central Silk Board": "ಸೆಂಟ್ರಲ್ ಸಿಲ್ಕ್ ಬೋರ್ಡ್",
    "Sir Puttanna Chetty Town Hall": "ಪುಟ್ಟಣ್ಣ ಚೆಟ್ಟಿ ಪುರಭವನ",
    "Bangalore Palace": "ಬೆಂಗಳೂರು ಅರಮನೆ",
    "Mahatma Gandhi Road": "ಎಂ ಜಿ ರಸ್ತೆ ಮೆಟ್ರೋ ನಿಲ್ದಾಣ",
    "Nexus Koramangala": "ನೆಕ್ಸಸ್ ಕೋರಮಂಗಲ (ಫೋರಂ ಮಾಲ್)",
    "Forum Mall": "ಫೋರಂ ಮಾಲ್ ಕೋರಮಂಗಲ",
    "Koramangala": "ಕೋರಮಂಗಲ",
    "Halasuru": "ಹಲಸೂರು",
    "Cubbon Park": "ಕಬ್ಬನ್ ಪಾರ್ಕ್",
    "Lalbagh": "ಲಾಲ್‌ಬಾಗ್",
    "Malleshwaram": "ಮಲ್ಲೇಶ್ವರಂ",
    "Jayanagar": "ಜಯನಗರ",
    "Shivajinagar": "ಶಿವಾಜಿನಗರ",
}


def get_aliases_for_entry(name: str) -> list[str]:
    """Return colloquial aliases for a given POI entry name."""
    if not name:
        return []
    aliases: list[str] = []
    for canonical, alias_list in CANONICAL_ALIASES.items():
        if canonical.lower() in name.lower() or name.lower() in canonical.lower():
            aliases.extend(alias_list)
    return aliases


def resolve_query_alias(norm_key: str) -> str | None:
    """If the normalized key matches a colloquial alias, return canonical search target."""
    return QUERY_ALIASES.get(norm_key)


def get_kannada_name(name: str, fallback_kn: str | None = None) -> str | None:
    """Return authentic Kannada name for a destination if available."""
    if fallback_kn:
        return fallback_kn
    if not name:
        return None
    for k, kn in CANONICAL_KN.items():
        if k.lower() in name.lower() or name.lower() in k.lower():
            return kn
    return None
