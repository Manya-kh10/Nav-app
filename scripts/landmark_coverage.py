"""Landmark coverage test: for 8 Bangalore walking routes, how many turns have a named OSM place nearby."""
import json
import math
import time
import hashlib
from pathlib import Path

import httpx

# (name, (lat, lon) start, (lat, lon) end) - coordinates are approximate, the router snaps to the nearest road
ROUTES = [
    ("MG Road Metro -> Cubbon Park", (12.9756, 77.6068), (12.9763, 77.5929)),
    ("Majestic -> Vidhana Soudha", (12.9767, 77.5713), (12.9796, 77.5907)),
    ("Indiranagar Metro -> 100 Feet Rd south", (12.9784, 77.6408), (12.9719, 77.6412)),
    ("Koramangala Sony World -> Forum Mall", (12.9352, 77.6245), (12.9346, 77.6110)),
    ("Jayanagar 4th Block -> Lalbagh West Gate", (12.9250, 77.5938), (12.9487, 77.5800)),
    ("Malleshwaram 18th Cross -> Mantri Square", (12.9998, 77.5700), (12.9915, 77.5713)),
    ("Shivajinagar Bus Stand -> Commercial St", (12.9857, 77.5990), (12.9822, 77.6083)),
    ("Bull Temple -> Jayanagar 4th Block", (12.9419, 77.5685), (12.9250, 77.5938)),
]

# dev-only public servers; foot server is tried first, car profile is the fallback
ROUTERS = [
    ("foot", "https://routing.openstreetmap.de/routed-foot/route/v1/driving/{c}"),
    ("car", "https://router.project-osrm.org/route/v1/driving/{c}"),
]
OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "bangalore-voice-nav-hackathon/0.1 (student project)"}

TURN_TYPES = {"turn", "fork", "end of road", "roundabout", "rotary", "roundabout turn"}
CACHE_DIR = Path(__file__).resolve().parent.parent / "eval" / "results" / "overpass_cache"
BAD_TYPES = {
    "parking", "bench", "waste_basket", "bicycle_parking", "parking_space", "parking_entrance",
    "toilets", "shelter", "post_box", "vending_machine", "drinking_water",
    "motorcycle_parking", "taxi", "information", "public_bookcase", "charging_station",
}
RADII = (30, 50)  # metres


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_route(client, start, end):
    coords = f"{start[1]},{start[0]};{end[1]},{end[0]}"
    for label, url in ROUTERS:
        try:
            r = client.get(url.format(c=coords), params={"overview": "false", "steps": "true"})
            data = r.json()
            if r.status_code == 200 and data.get("code") == "Ok":
                return label, data["routes"][0]
        except Exception as e:
            print(f"   router {label} failed: {e}")
    return None, None


def extract_turns(route):
    turns = []
    for leg in route["legs"]:
        for step in leg["steps"]:
            m = step["maneuver"]
            if m["type"] in TURN_TYPES and m.get("modifier") != "straight":
                turns.append({
                    "lat": m["location"][1], "lon": m["location"][0],
                    "what": f'{m["type"]} {m.get("modifier", "")}'.strip(),
                    "road": step.get("name", ""),
                })
    return turns


def fetch_pois(client, turns):
    pad = 0.001
    s = min(t["lat"] for t in turns) - pad
    n = max(t["lat"] for t in turns) + pad
    w = min(t["lon"] for t in turns) - pad
    e = max(t["lon"] for t in turns) + pad
    box = f"({s},{w},{n},{e})"
    query = (
        "[out:json][timeout:60];("
        f'nwr["name"][~"^(amenity|shop|tourism|leisure)$"~"."]{box};'
        f'nwr["name"]["railway"="station"]{box};'
        ");out center tags;"
    )
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / (hashlib.md5(query.encode()).hexdigest() + ".json")
    if cache.exists():
        return parse_pois(json.loads(cache.read_text(encoding="utf-8")))
    for attempt in range(3):
        for url in OVERPASS:
            try:
                r = client.post(url, data={"data": query}, timeout=120)
                if r.status_code == 200:
                    els = r.json()["elements"]
                    cache.write_text(json.dumps(els), encoding="utf-8")
                    return parse_pois(els)
                print(f"   overpass {url} -> HTTP {r.status_code}")
            except Exception as ex:
                print(f"   overpass failed: {ex}")
        wait = 10 * (attempt + 1)
        print(f"   retrying in {wait}s")
        time.sleep(wait)
    return None


def parse_pois(elements):
    pois = []
    for el in elements:
        tags = el.get("tags", {})
        kind = next((tags[k] for k in ("amenity", "shop", "tourism", "leisure", "railway") if k in tags), None)
        if kind is None or kind in BAD_TYPES:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        pois.append({"name": tags["name"], "kind": kind, "lat": lat, "lon": lon})
    return pois


def main():
    root = Path(__file__).resolve().parent.parent
    results = []
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for name, start, end in ROUTES:
            print(f"-> {name}")
            profile, route = get_route(client, start, end)
            if not route:
                print("   no route, skipped")
                continue
            turns = extract_turns(route)
            if not turns:
                print("   no turns found, skipped")
                continue
            pois = fetch_pois(client, turns)
            if pois is None:
                print("   no POI data, skipped")
                continue
            hits = {r: 0 for r in RADII}
            samples = []
            for t in turns:
                best = min(
                    ((haversine(t["lat"], t["lon"], p["lat"], p["lon"]), p) for p in pois),
                    key=lambda x: x[0], default=(None, None),
                )
                d, p = best
                if d is not None:
                    for r in RADII:
                        if d <= r:
                            hits[r] += 1
                    if d <= RADII[-1] and len(samples) < 3:
                        samples.append(f'{p["name"]} ({p["kind"]}, {int(d)}m)')
            results.append({
                "route": name, "profile": profile, "turns": len(turns),
                "distance_m": round(route["distance"]), "covered": hits, "samples": samples,
            })
            time.sleep(2)  # be polite to public servers

    print("\n" + "=" * 92)
    print(f'{"Route":42} {"Prof":5} {"Dist":>6} {"Turns":>5} {"<=30m":>9} {"<=50m":>9}')
    print("-" * 92)
    tt = {r: 0 for r in RADII}
    total_turns = 0
    for r in results:
        total_turns += r["turns"]
        cells = []
        for rad in RADII:
            tt[rad] += r["covered"][rad]
            cells.append(f'{r["covered"][rad]}/{r["turns"]}')
        print(f'{r["route"][:42]:42} {r["profile"]:5} {r["distance_m"]:>5}m {r["turns"]:>5} {cells[0]:>9} {cells[1]:>9}')
    print("-" * 92)
    if total_turns:
        print(f'{"TOTAL":42} {"":5} {"":>6} {total_turns:>5} '
              f'{tt[30]}/{total_turns} ({100 * tt[30] // total_turns}%)  '
              f'{tt[50]}/{total_turns} ({100 * tt[50] // total_turns}%)')
    print("\nSample landmarks found:")
    for r in results:
        print(f'  {r["route"]}: {"; ".join(r["samples"]) or "none"}')

    out = root / "eval" / "results" / "landmark_coverage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()