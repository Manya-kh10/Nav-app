import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.places.matcher import PlaceIndex, make_key, tokens_of

ENTRIES = [
    {"name": "Indiranagar", "kind": "suburb", "lat": 12.9784, "lon": 77.6408},
    {"name": "Indiranagar Metro Station", "kind": "station", "lat": 12.9783, "lon": 77.6386},
    {"name": "MG Road Metro Station", "kind": "station", "lat": 12.9756, "lon": 77.6068},
    {"name": "Forum Mall", "kind": "mall", "lat": 12.9346, "lon": 77.6110},
    {"name": "Koramangala", "kind": "suburb", "lat": 12.9352, "lon": 77.6245},
    {"name": "Halasuru", "name_kn": "ಹಲಸೂರು", "kind": "station", "lat": 12.9766, "lon": 77.6266},
    {"name": "Cafe Coffee Day", "kind": "cafe", "lat": 12.9756, "lon": 77.6065},
    {"name": "Kempegowda Bus Station", "kind": "bus_station", "lat": 12.9781, "lon": 77.5724},
    {"name": "Krishna Rajendra Market", "kind": "station", "lat": 12.9608, "lon": 77.5746},
]
IDX = PlaceIndex(ENTRIES)


def names(q):
    return [p.name for p in IDX.search(q)]


def test_script_conversion():
    assert make_key(tokens_of("इंदिरानगर")) == "indiranagar"
    assert make_key(tokens_of("ಇಂದಿರಾನಗರ")) == "indiranagar"


def test_spacing():
    assert names("Indira Nagar")[0] == "Indiranagar"


def test_spelling_errors():
    assert "Indiranagar Metro Station" in names("indra nagar metro")[:2]
    assert "Indiranagar Metro Station" in names("indiranagr metro stn")[:2]
    assert names("koramangla")[0] == "Koramangala"


def test_hindi_and_kannada_script():
    assert "Indiranagar Metro Station" in names("इंदिरानगर मेट्रो स्टेशन")[:2]
    assert "Indiranagar Metro Station" in names("ಇಂದಿರಾನಗರ ಮೆಟ್ರೋ ಸ್ಟೇಷನ್")[:2]
    assert names("ಹಲಸೂರು")[0] == "Halasuru"


def test_spoken_sentence():
    assert names("MG Road metro kaise jaaun")[0] == "MG Road Metro Station"
    assert names("take me to Forum Mall please")[0] == "Forum Mall"


def test_colloquial_aliases():
    assert names("Majestic bus stand")[0] == "Kempegowda Bus Station"
    assert names("मजेस्टिक बस स्टैंड")[0] == "Kempegowda Bus Station"
    assert names("kr market")[0] == "Krishna Rajendra Market"
    assert names("k r market")[0] == "Krishna Rajendra Market"
    assert names("के आर मार्केट")[0] == "Krishna Rajendra Market"


def test_kannada_name_populated():
    res = IDX.search("Halasuru", 1)
    assert res[0].name_kn == "ಹಲಸೂರು"
    res = IDX.search("Kempegowda Bus Station", 1)
    assert res[0].name_kn == "ಕೆಂಪೇಗೌಡ ಬಸ್ ನಿಲ್ದಾಣ"


def test_nonsense_returns_nothing():
    assert names("qqqqqq") == []
