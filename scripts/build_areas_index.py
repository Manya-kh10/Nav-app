"""Download Bangalore neighbourhood / locality names from Overpass into data\\bangalore_areas.json."""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "bangalore_areas.json"
SOUTH, NORTH, WEST, EAST = 12.83, 13.14, 77.46, 77.76
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "bangalore-voice-nav-hackathon/0.1 (student project)"}
QUERY = (
    "[out:json][timeout:90];("
    'node["name"]["place"~"^(suburb|neighbourhood|quarter|locality|village|town|hamlet)$"]'
    f"({SOUTH},{WEST},{NORTH},{EAST});"
    ");out tags center;"
)


def main():
    elements = None
    with httpx.Client(headers=HEADERS) as client:
        for attempt in range(3):
            for url in MIRRORS:
                try:
                    r = client.post(url, data={"data": QUERY}, timeout=150)
                    if r.status_code == 200:
                        elements = r.json()["elements"]
                        break
                    print(f"{url.split('/')[2]} -> HTTP {r.status_code}")
                except Exception as ex:
                    print(f"{url.split('/')[2]} failed: {type(ex).__name__}")
            if elements is not None:
                break
            wait = 15 * (attempt + 1)
            print(f"retrying in {wait}s")
            time.sleep(wait)
    if elements is None:
        print("Could not download. Wait a few minutes and run this again.")
        return
    out = []
    for el in elements:
        t = el.get("tags", {})
        if "name" not in t or "lat" not in el:
            continue
        out.append({"name": t["name"], "name_en": t.get("name:en"), "name_kn": t.get("name:kn"),
                    "kind": t["place"], "lat": el["lat"], "lon": el["lon"]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(out)} areas -> {OUT}")


if __name__ == "__main__":
    main()