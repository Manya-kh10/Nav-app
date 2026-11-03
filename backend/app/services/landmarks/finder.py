import json
import math

from app.core.config import ROOT
from app.schemas.route import Step

INDEX = ROOT / "data" / "bangalore_pois.json"
MAX_DIST_M = 40
_pois: list[dict] | None = None


def _load() -> list[dict] | None:
    global _pois
    if _pois is None and INDEX.exists():
        _pois = json.loads(INDEX.read_text(encoding="utf-8"))
    return _pois


def _haversine(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def find_landmarks(steps: list[Step]) -> dict[int, dict] | None:
    """{step_index: {name, kind}} for turns with a verified named place within 40 m; None if the index is missing."""
    pois = _load()
    if pois is None:
        return None
    result: dict[int, dict] = {}
    for i, st in enumerate(steps):
        if st.maneuver in ("depart", "arrive"):
            continue
        best = None
        for p in pois:
            if abs(p["lat"] - st.lat) > 0.0005 or abs(p["lon"] - st.lon) > 0.0005:
                continue
            d = _haversine(st.lat, st.lon, p["lat"], p["lon"])
            if d <= MAX_DIST_M and (best is None or d < best[0]):
                best = (d, p)
        if best:
            p = best[1]
            result[i] = {"name": p.get("name_en") or p["name"], "kind": p["kind"]}
    return result