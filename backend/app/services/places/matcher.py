import json
import re

from rapidfuzz import fuzz, process

from app.core.config import ROOT
from app.schemas.places import Place
from app.services.places.aliases import get_aliases_for_entry, resolve_query_alias
from app.services.places.translit import to_latin

MIN_SCORE = 62.0

FILLER = {
    "the", "to", "from", "near", "nearest", "at", "in", "on", "me", "my", "i", "want", "need",
    "go", "going", "take", "navigate", "navigation", "directions", "direction", "route", "how",
    "do", "can", "get", "reach", "find", "show", "search", "where", "is", "are", "please",
    "kaise", "jaun", "jaaun", "jana", "jaana", "jao", "jaye", "chahiye", "chalo", "batao",
    "bataiye", "bataye", "ka", "ke", "ki", "ko", "mein", "tak", "pe", "par", "hai", "hain",
    "hoon", "mujhe", "wahan", "kidhar", "kahan", "kaha",
    "bangalore", "bengaluru", "bengalooru", "bangaluru", "blr",
}
ABBREV = {"stn": "station", "sta": "station", "stat": "station", "rd": "road", "cir": "circle",
          "jn": "junction", "jnc": "junction", "hosp": "hospital"}
HINTS = {
    "metro": {"station"}, "station": {"station", "bus_station"}, "railway": {"station"},
    "bus": {"bus_station"}, "stand": {"bus_station"}, "mall": {"mall", "department_store"},
    "hospital": {"hospital", "clinic"}, "temple": {"place_of_worship"},
    "church": {"place_of_worship"}, "masjid": {"place_of_worship"}, "mosque": {"place_of_worship"},
    "school": {"school"}, "college": {"college"}, "market": {"marketplace", "supermarket"},
    "bank": {"bank"}, "pharmacy": {"pharmacy"}, "hotel": {"hotel"},
}
AREA_KINDS = {"suburb", "neighbourhood", "quarter", "locality", "town", "village", "hamlet"}
KIND_BONUS = {"station": 3, "bus_station": 3, "suburb": 3, "neighbourhood": 3, "town": 3,
              "quarter": 2, "locality": 2, "mall": 2, "hospital": 2, "college": 1, "village": 1}
KIND_LABEL = {"station": "station", "bus_station": "bus station", "place_of_worship": "place of worship",
              "fast_food": "fast food", **{k: "area" for k in AREA_KINDS}}


def _collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def tokens_of(text: str) -> list[str]:
    latin = re.sub(r"[^a-z0-9]+", " ", to_latin(text).lower())
    latin = re.sub(r"\bk\s+r\b", "kr", latin)
    latin = re.sub(r"\bm\s+g\b", "mg", latin)
    toks = [ABBREV.get(t, t) for t in latin.split()]
    kept = [t for t in toks if t not in FILLER]
    return kept or toks


def make_key(tokens: list[str]) -> str:
    return _collapse("".join(tokens))


def skeleton(key: str) -> str:
    """Consonant skeleton: Indira, Indra and the Hindi/Kannada spellings all end up the same."""
    s = re.sub(r"chh?", "C", key)
    s = s.replace("sh", "S")
    s = re.sub(r"([kgjtdpb])h", r"\1", s)
    s = s.translate(str.maketrans({"c": "k", "q": "k", "x": "k", "z": "j", "f": "p", "w": "v"}))
    s = re.sub(r"[aeiou]", "", s)
    return _collapse(s)


def _score(qk: str, qs: str, ek: str, es: str) -> float:
    s = float(fuzz.ratio(qk, ek))
    k = fuzz.ratio(qs, es) * 0.97 if qs and es else 0.0
    p = fuzz.partial_ratio(qk, ek) * (0.9 if len(qk) <= len(ek) else 0.85) if len(qk) >= 5 else 0.0
    ps = 0.0
    if len(qs) >= 4 and len(es) >= 3:
        ps = fuzz.partial_ratio(qs, es) * (0.88 if len(qs) <= len(es) else 0.8)
    return max(s, k, p, ps)


def score_text(query: str, text: str) -> float:
    qk, ek = make_key(tokens_of(query)), make_key(tokens_of(text))
    if len(qk) < 3 or len(ek) < 2:
        return 0.0
    return _score(qk, skeleton(qk), ek, skeleton(ek))


def _label(kind: str) -> str:
    return KIND_LABEL.get(kind, kind.replace("_", " "))


class PlaceIndex:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.keys: list[str] = []
        self.skels: list[str] = []
        self.owner: list[int] = []
        self.areas: list[tuple[float, float, str]] = []
        for idx, e in enumerate(entries):
            if e.get("kind") in AREA_KINDS:
                self.areas.append((e["lat"], e["lon"], e.get("name_en") or e["name"]))
            seen: set[str] = set()
            names_to_index = [e.get("name_en"), e.get("name"), e.get("name_kn")]
            names_to_index.extend(get_aliases_for_entry(e.get("name") or ""))
            for nm in names_to_index:
                if not nm:
                    continue
                k = make_key(tokens_of(nm))
                if len(k) < 2 or k in seen:
                    continue
                seen.add(k)
                self.keys.append(k)
                self.skels.append(skeleton(k))
                self.owner.append(idx)

    def _nearest_area(self, lat: float, lon: float) -> str | None:
        best = None
        for alat, alon, name in self.areas:
            dy = (alat - lat) * 111320
            dx = (alon - lon) * 108500
            d = dx * dx + dy * dy
            if best is None or d < best[0]:
                best = (d, name)
        return best[1] if best and best[0] <= 3000 ** 2 else None

    def search(self, query: str, limit: int = 5) -> list[Place]:
        toks = tokens_of(query)
        qk = make_key(toks)
        if len(qk) < 3 or not self.keys:
            return []
        qs = skeleton(qk)
        hints: set[str] = set()
        for t in toks:
            hints |= HINTS.get(t, set())

        cand: set[int] = set()
        for _, _, i in process.extract(qk, self.keys, scorer=fuzz.ratio, limit=60, score_cutoff=55):
            cand.add(i)
        for _, _, i in process.extract(qk, self.keys, scorer=fuzz.partial_ratio, limit=80, score_cutoff=75):
            cand.add(i)
        if len(qs) >= 3:
            for _, _, i in process.extract(qs, self.skels, scorer=fuzz.ratio, limit=60, score_cutoff=60):
                cand.add(i)
            for _, _, i in process.extract(qs, self.skels, scorer=fuzz.partial_ratio, limit=80, score_cutoff=80):
                cand.add(i)

        alias_target = resolve_query_alias(qk)
        atk = make_key(tokens_of(alias_target)) if alias_target else ""
        ats = skeleton(atk) if atk else ""
        if atk:
            for _, _, i in process.extract(atk, self.keys, scorer=fuzz.ratio, limit=30, score_cutoff=60):
                cand.add(i)
            for _, _, i in process.extract(atk, self.keys, scorer=fuzz.partial_ratio, limit=40, score_cutoff=70):
                cand.add(i)

        best: dict[int, float] = {}
        for i in cand:
            sc = _score(qk, qs, self.keys[i], self.skels[i])
            if atk:
                sc = max(sc, _score(atk, ats, self.keys[i], self.skels[i]))
            o = self.owner[i]
            if sc > best.get(o, 0.0):
                best[o] = sc

        scored = []
        for o, sc in best.items():
            kind = self.entries[o].get("kind", "")
            if kind in hints:
                sc += 5
            sc = min(100.0, sc + KIND_BONUS.get(kind, 0))
            if sc >= MIN_SCORE:
                scored.append((sc, o))
        scored.sort(key=lambda x: -x[0])

        out: list[Place] = []
        chosen: list[tuple[str, float, float]] = []
        per_key: dict[str, int] = {}
        for sc, o in scored:
            e = self.entries[o]
            name = e.get("name_en") or e["name"]
            k = make_key(tokens_of(name))
            if per_key.get(k, 0) >= 2:
                continue
            if any(k == ck and abs(e["lat"] - la) < 0.0015 and abs(e["lon"] - lo) < 0.0015
                   for ck, la, lo in chosen):
                continue
            per_key[k] = per_key.get(k, 0) + 1
            chosen.append((k, e["lat"], e["lon"]))
            kind = e.get("kind", "")
            disp = f"{name} ({_label(kind)})"
            if kind not in AREA_KINDS:
                area = self._nearest_area(e["lat"], e["lon"])
                if area and make_key(tokens_of(area)) != k:
                    disp += f", near {area}"
            out.append(Place(name=name, display_name=disp, lat=e["lat"], lon=e["lon"],
                             category="local", type=kind, score=round(sc, 1), source="local"))
            if len(out) >= limit:
                break
        return out


_index: PlaceIndex | None = None


def get_index() -> PlaceIndex:
    global _index
    if _index is None:
        entries: list[dict] = []
        for fn in ("bangalore_areas.json", "bangalore_pois.json"):
            p = ROOT / "data" / fn
            if p.exists():
                entries.extend(json.loads(p.read_text(encoding="utf-8")))
        from app.services.places.aliases import PROMINENT_PLACES
        entries.extend(PROMINENT_PLACES)
        _index = PlaceIndex(entries)
    return _index
