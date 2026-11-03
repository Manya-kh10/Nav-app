"""One-time build of a local Bangalore landmark index from Overpass (tiled, cached, safe to re-run)."""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
TILE_DIR = ROOT / "data" / "poi_tiles"
OUT = ROOT / "data" / "bangalore_pois.json"

SOUTH, NORTH, WEST, EAST = 12.83, 13.14, 77.46, 77.76
ROWS, COLS = 4, 4
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "bangalore-voice-nav-hackathon/0.1 (student project)"}

AMENITIES = ("place_of_worship|bank|pharmacy|hospital|clinic|school|college|fuel|restaurant|"
             "cafe|fast_food|marketplace|cinema|police|post_office|bus_station|library")
SHOPS = "supermarket|bakery|convenience|mall|department_store"


def tile_query(s, w, n, e):
    box = f"({s},{w},{n},{e})"
    return (
        "[out:json][timeout:90];("
        f'nwr["name"]["amenity"~"^({AMENITIES})$"]{box};'
        f'nwr["name"]["shop"~"^({SHOPS})$"]{box};'
        f'nwr["name"]["tourism"="hotel"]{box};'
        f'nwr["name"]["railway"="station"]{box};'
        ");out center tags;"
    )


def fetch_tile(client, query):
    for attempt in range(3):
        for url in MIRRORS:
            try:
                r = client.post(url, data={"data": query}, timeout=150)
                if r.status_code == 200:
                    return r.json()["elements"]
                print(f"   {url.split('/')[2]} -> HTTP {r.status_code}")
            except Exception as ex:
                print(f"   {url.split('/')[2]} failed: {type(ex).__name__}")
        wait = 15 * (attempt + 1)
        print(f"   retrying in {wait}s")
        time.sleep(wait)
    return None


def to_poi(el):
    tags = el.get("tags", {})
    kind = next((tags[k] for k in ("amenity", "shop", "tourism", "railway") if k in tags), None)
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    if kind is None or lat is None or lon is None or "name" not in tags:
        return None
    return {"name": tags["name"], "name_en": tags.get("name:en"), "name_kn": tags.get("name:kn"),
            "kind": kind, "lat": lat, "lon": lon}


def main():
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    dlat, dlon = (NORTH - SOUTH) / ROWS, (EAST - WEST) / COLS
    missing = []
    with httpx.Client(headers=HEADERS) as client:
        for r in range(ROWS):
            for c in range(COLS):
                f = TILE_DIR / f"tile_{r}_{c}.json"
                if f.exists():
                    continue
                s, w = SOUTH + r * dlat, WEST + c * dlon
                print(f"tile {r},{c} ...")
                els = fetch_tile(client, tile_query(round(s, 5), round(w, 5), round(s + dlat, 5), round(w + dlon, 5)))
                if els is None:
                    missing.append((r, c))
                    continue
                f.write_text(json.dumps(els), encoding="utf-8")
                print(f"   {len(els)} elements")
                time.sleep(5)

    pois = {}
    for f in TILE_DIR.glob("tile_*.json"):
        for el in json.loads(f.read_text(encoding="utf-8")):
            p = to_poi(el)
            if p:
                pois[f'{el["type"]}{el["id"]}'] = p
    OUT.write_text(json.dumps(list(pois.values()), ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(pois)} places -> {OUT}")
    if missing:
        print(f"Missing tiles {missing}. Wait a few minutes and run this script again.")


if __name__ == "__main__":
    main()